from dotenv import load_dotenv 
import os 
import psycopg2 

load_dotenv() 
uri = os.environ["SUPABASE_DB_URL"] 
conn = psycopg2.connect(uri) 
print("connexion OK") 
cur = conn.cursor() 
cur.execute("SELECT count(*) FROM annonces_boamp;") 
print("nombre de lignes dans la table annonces_boamp :", cur.fetchone()[0]) 
conn.close()