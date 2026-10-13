"""M2 - Agentic AI - Improving SQL Generation with Reflection.

This file follows the lab flow:
1) Setup environment and client
2) Generate SQL from natural language (V1)
3) Reflect and refine SQL (V2)
4) Use execution feedback for stronger refinement
5) Run full end-to-end workflow
"""

import json
import os

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine


# ============================================================
# 2. Setup: Initialize Environment and Client
# ============================================================
_ = load_dotenv()
client = OpenAI()

DB_URL = os.getenv(
	"DATABASE_URL",
	"postgresql://postgres@localhost:5432/postgres",
)

DEFAULT_MODEL = "gpt-5.2"


def _response_text(response) -> str:
	text = getattr(response, "output_text", None)
	if text:
		return str(text).strip()
	return str(response).strip()


def get_schema(db_url: str) -> str:
	engine = create_engine(db_url)
	query = """
		SELECT table_name, column_name, data_type
		FROM information_schema.columns
		WHERE table_schema = 'public'
		ORDER BY table_name, ordinal_position;
	"""
	df = pd.read_sql(query, engine)
	if df.empty:
		return "No tables found in public schema."

	lines: list[str] = []
	for table_name, group in df.groupby("table_name"):
		lines.append(f"Table: {table_name}")
		for _, row in group.iterrows():
			lines.append(f"  - {row['column_name']}: {row['data_type']}")
	return "\n".join(lines)


def execute_sql(sql_query: str, db_url: str) -> pd.DataFrame:
	engine = create_engine(db_url)
	return pd.read_sql(sql_query, engine)


# ============================================================
# 3. Build a SQL Generator
# ============================================================
def generate_sql(question: str, schema_text: str, model: str = DEFAULT_MODEL) -> str:
	prompt = f"""
You are a SQL assistant. Given the schema and the user's question, write a SQL query for PostgreSQL.

Schema:
{schema_text}

User question:
{question}

Respond with the SQL only.
"""
	response = client.responses.create(
		model=model,
		input=prompt,
	)
	return _response_text(response)


# ============================================================
# 3.2 Reflection: SQL-only review
# ============================================================
def refine_sql(
	question: str,
	sql_query: str,
	schema_text: str,
	model: str = DEFAULT_MODEL,
) -> tuple[str, str]:
	"""Review SQL text against the question and schema.

	Returns:
		(feedback, refined_sql)
	"""
	prompt = f"""
You are a SQL reviewer and refiner.

User asked:
{question}

Original SQL:
{sql_query}

Table Schema:
{schema_text}

Step 1: Briefly evaluate if the SQL OUTPUT fully answers the user's question.
Step 2: If improvement is needed, provide a refined SQL query for PostgreSQL.
If the original SQL is already correct, return it unchanged.

Return STRICT JSON with two fields:
{{
  "feedback": "<1-3 sentences explaining the gap or confirming correctness>",
  "refined_sql": "<final SQL to run>"
}}
"""
	response = client.responses.create(
		model=model,
		input=prompt,
	)

	content = _response_text(response)
	try:
		obj = json.loads(content)
		feedback = str(obj.get("feedback", "")).strip()
		refined_sql = str(obj.get("refined_sql", sql_query)).strip()
		if not refined_sql:
			refined_sql = sql_query
	except Exception:
		feedback = content.strip()
		refined_sql = sql_query

	return feedback, refined_sql


# ============================================================
# 3.2.2 Reflection with external feedback (execution output)
# ============================================================
def refine_sql_external_feedback(
	question: str,
	sql_query: str,
	df_feedback: pd.DataFrame,
	schema_text: str,
	model: str = DEFAULT_MODEL,
) -> tuple[str, str]:
	"""Review SQL using actual execution output.

	Returns:
		(feedback, refined_sql)
	"""
	prompt = f"""
You are a SQL reviewer and refiner.

User asked:
{question}

Original SQL:
{sql_query}

SQL Output:
{df_feedback.to_markdown(index=False)}

Table Schema:
{schema_text}

Step 1: Briefly evaluate if the SQL output answers the user's question.
Step 2: If the SQL could be improved, provide a refined SQL query.
If the original SQL is already correct, return it unchanged.

Return a strict JSON object with two fields:
- "feedback": brief evaluation and suggestions
- "refined_sql": the final SQL to run
"""
	response = client.responses.create(
		model=model,
		input=prompt,
	)

	content = _response_text(response)
	try:
		obj = json.loads(content)
		feedback = str(obj.get("feedback", "")).strip()
		refined_sql = str(obj.get("refined_sql", sql_query)).strip()
		if not refined_sql:
			refined_sql = sql_query
	except Exception:
		feedback = content.strip()
		refined_sql = sql_query

	return feedback, refined_sql


# ============================================================
# 3.3 End-to-End Workflow
# ============================================================
def run_sql_workflow(
	db_url: str,
	question: str,
	model_generation: str = DEFAULT_MODEL,
	model_evaluation: str = DEFAULT_MODEL,
	) -> dict[str, object]:
	"""Generate, execute, reflect, refine, and execute again.

	Returns a general-purpose payload without display formatting.
	"""
	schema_text = get_schema(db_url)
	sql_v1 = generate_sql(question, schema_text, model_generation)
	df_v1 = execute_sql(sql_v1, db_url)

	feedback, sql_v2 = refine_sql_external_feedback(
		question=question,
		sql_query=sql_v1,
		df_feedback=df_v1,
		schema_text=schema_text,
		model=model_evaluation,
	)
	df_v2 = execute_sql(sql_v2, db_url)

	return {
		"question": question,
		"schema": schema_text,
		"sql_v1": sql_v1,
		"sql_v2": sql_v2,
		"feedback": feedback,
		"result_v1": df_v1,
		"result_v2": df_v2,
	}


if __name__ == "__main__":
	try:
		run_sql_workflow(
			db_url=DB_URL,
			question="Example question here",
			model_generation=DEFAULT_MODEL,
			model_evaluation=DEFAULT_MODEL,
		)
	except Exception:
		pass
