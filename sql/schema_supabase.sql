-- Schéma Supabase de la veille BOAMP : table annonces_boamp, accès depuis la
-- page web, traçabilité des annotations.
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
    note_humaine                smallint CHECK (note_humaine BETWEEN 0 AND 5),
    annotation_par              text,
    annotation_le               timestamptz,
    PRIMARY KEY (id)
);

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
