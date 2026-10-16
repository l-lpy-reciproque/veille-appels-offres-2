-- Schéma Supabase de la veille : tables annonces_boamp et annonces_ted, accès
-- depuis la page web, traçabilité des annotations.
--
-- Reflète l'état de la base au 14/10/2026. À exécuter dans le SQL editor de
-- Supabase pour recréer un projet. Relançable sans effet sur une base déjà à
-- jour (IF NOT EXISTS, DROP … IF EXISTS, OR REPLACE).
--
-- À faire en plus dans le tableau de bord (pas faisable en SQL) :
--   - Authentication → Sign In / Providers : désactiver « Allow new users to sign up » ;
--   - Authentication → Users → Add user : créer les comptes (email + mot de passe, « Auto confirm »).

-- 1. Table ------------------------------------------------------------------
--    Colonnes match_* : une par entrée de tagging.CLUSTERS.

CREATE TABLE IF NOT EXISTS annonces_boamp (
    id                          serial,
    idweb                       text NOT NULL UNIQUE,
    objet                       text,
    nomacheteur                 text,
    code_departement            text,
    dateparution                text,          -- AAAA-MM-JJ
    datelimitereponse           text,          -- ISO 8601
    famille_libelle             text,
    descripteur_libelle         text,
    procedure_libelle           text,
    url_avis                    text,
    score_similarite            double precision,
    date_ingestion              timestamptz DEFAULT now(),
    match_prestations           integer,
    match_numerique_multimedia  integer,
    match_museo_sceno           integer,
    match_secteurs_transverses  integer,
    match_institutions          integer,
    total_poles                 integer,
    rapporte                    boolean NOT NULL DEFAULT false,
    analyse_pertinence          text,
    analyse_note                smallint,
    -- Colonnes de l'équipe, écrites uniquement depuis la page web.
    vue                         boolean NOT NULL DEFAULT false,
    -- 1 = non pertinent, 2 = partiellement pertinent, 3 = pertinent.
    note_humaine                smallint,
    annotation_par              text,
    annotation_le               timestamptz,
    PRIMARY KEY (id)
);

ALTER TABLE annonces_boamp DROP CONSTRAINT IF EXISTS annonces_boamp_note_humaine_check;
ALTER TABLE annonces_boamp DROP CONSTRAINT IF EXISTS note_humaine_0_5;
ALTER TABLE annonces_boamp DROP CONSTRAINT IF EXISTS note_humaine_1_3;
ALTER TABLE annonces_boamp ADD CONSTRAINT note_humaine_1_3
    CHECK (note_humaine IS NULL OR note_humaine BETWEEN 1 AND 3);

-- 2. Accès depuis la page web -----------------------------------------------
--    Lecture réservée aux utilisateurs connectés ; seules vue et note_humaine
--    sont modifiables. Le rôle anon (clé publishable sans connexion) n'a aucun
--    droit. La pipeline se connecte en propriétaire et n'est pas concernée.

ALTER TABLE annonces_boamp ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS lecture ON annonces_boamp;
CREATE POLICY lecture ON annonces_boamp
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS maj ON annonces_boamp;
CREATE POLICY maj ON annonces_boamp
    FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

REVOKE ALL ON annonces_boamp FROM anon, authenticated;
GRANT SELECT ON annonces_boamp TO authenticated;
GRANT UPDATE (vue, note_humaine) ON annonces_boamp TO authenticated;

-- 3. Traçabilité ------------------------------------------------------------
--    Qui a modifié vue / note_humaine en dernier, et quand. Ne se déclenche
--    que si l'une des deux colonnes change : les upserts quotidiens de la
--    pipeline ne touchent pas annotation_par / annotation_le.

CREATE OR REPLACE FUNCTION tracer_annotation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.vue IS DISTINCT FROM OLD.vue
       OR NEW.note_humaine IS DISTINCT FROM OLD.note_humaine THEN
        NEW.annotation_par := auth.jwt() ->> 'email';
        NEW.annotation_le := now();
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS tracer_annotation ON annonces_boamp;
CREATE TRIGGER tracer_annotation
    BEFORE UPDATE ON annonces_boamp
    FOR EACH ROW EXECUTE FUNCTION tracer_annotation();

-- 4. Table annonces_ted -----------------------------------------------------
--    Appels d'offres européens TED (src/ingestion_ted.py), mêmes colonnes de
--    pipeline et d'équipe que annonces_boamp, mêmes droits, même trigger.
--    idweb = numéro de publication TED (ex. 696588-2026). Les textes sont dans
--    la langue d'origine ; titre_fr = « Pays – libellé CPV – titre d'origine ».

CREATE TABLE IF NOT EXISTS annonces_ted (
    id                          serial PRIMARY KEY,
    idweb                       text NOT NULL UNIQUE,
    objet                       text,          -- titre, langue d'origine
    objet_fr                    text,          -- traduction automatique (avis non francophones retenus pour traduction)
    titre_fr                    text,
    description                 text,          -- langue d'origine
    langue                      text,          -- code ISO 639-3 (fra, deu, pol…)
    nomacheteur                 text,
    nomacheteur_fr              text,          -- traduction automatique, idem
    pays                        text,          -- codes ISO 3166-1 alpha-3 (FRA, DEU…)
    ville                       text,
    dateparution                text,          -- AAAA-MM-JJ
    datelimitereponse           text,          -- AAAA-MM-JJ, dernière échéance des lots
    type_avis                   text,          -- cn-standard, pin-cfc-standard…
    procedure_libelle           text,          -- open, restricted…
    codes_cpv                   text,          -- tous les codes de l'avis
    libelles_cpv                text,          -- libellés français des codes de donnees/codes_cpv.csv
    url_avis                    text,
    score_similarite            double precision,
    date_ingestion              timestamptz DEFAULT now(),
    match_prestations           integer,
    match_numerique_multimedia  integer,
    match_museo_sceno           integer,
    match_secteurs_transverses  integer,
    match_institutions          integer,
    total_poles                 integer,
    rapporte                    boolean NOT NULL DEFAULT false,
    analyse_pertinence          text,
    analyse_note                smallint,
    -- Colonnes de l'équipe, écrites uniquement depuis la page web.
    vue                         boolean NOT NULL DEFAULT false,
    -- 1 = non pertinent, 2 = partiellement pertinent, 3 = pertinent.
    note_humaine                smallint,
    annotation_par              text,
    annotation_le               timestamptz,
    CONSTRAINT ted_note_humaine_1_3
        CHECK (note_humaine IS NULL OR note_humaine BETWEEN 1 AND 3)
);

-- Ajoutées le 16/10/2026, après la création de la table.
ALTER TABLE annonces_ted ADD COLUMN IF NOT EXISTS objet_fr text;
ALTER TABLE annonces_ted ADD COLUMN IF NOT EXISTS nomacheteur_fr text;

ALTER TABLE annonces_ted ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS lecture ON annonces_ted;
CREATE POLICY lecture ON annonces_ted
    FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS maj ON annonces_ted;
CREATE POLICY maj ON annonces_ted
    FOR UPDATE TO authenticated USING (true) WITH CHECK (true);

REVOKE ALL ON annonces_ted FROM anon, authenticated;
GRANT SELECT ON annonces_ted TO authenticated;
GRANT UPDATE (vue, note_humaine) ON annonces_ted TO authenticated;

DROP TRIGGER IF EXISTS tracer_annotation ON annonces_ted;
CREATE TRIGGER tracer_annotation
    BEFORE UPDATE ON annonces_ted
    FOR EACH ROW EXECUTE FUNCTION tracer_annotation();
