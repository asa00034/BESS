
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
import psycopg2

load_dotenv()
database_url = os.getenv("DATABASE_URL", "postgresql://postgres@localhost:5432/postgres")

# Read CSV file
df = pd.read_csv(r'C:\Users\Azmee\Downloads\opendss_ae_features_500_decentralized.csv')


engine = create_engine(database_url)


database = psycopg2.connect(database_url)
