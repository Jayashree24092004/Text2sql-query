import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text, inspect
from dotenv import load_dotenv
import os
from groq import Groq


# =========================
# LOAD ENV
# =========================




load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if api_key is None:
    raise ValueError(
        "GROQ_API_KEY not found. Check .env file."
    )

client = Groq(
    api_key=api_key
)

# =========================
# DATABASE
# =========================

from sqlalchemy import create_engine

DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(DATABASE_URL)

# =========================
# STREAMLIT CONFIG
# =========================

st.set_page_config(
    page_title="AI SQL Assistant",
    layout="wide"
)

st.title("AI SQL Assistant using Grok")

# =========================
# FILE UPLOAD
# =========================

# =========================
# FILE UPLOAD
# =========================

uploaded_files = st.file_uploader(
    "Upload Multiple CSV Files",
    type=["csv"],
    accept_multiple_files=True
)

all_tables = []

if uploaded_files:

    for uploaded_file in uploaded_files:

        try:

            # READ CSV
            df = pd.read_csv(uploaded_file)

            # CLEAN TABLE NAME
            table_name = uploaded_file.name.replace(".csv", "")
            table_name = table_name.replace(" ", "_")
            table_name = table_name.lower()

            # STORE TABLE
            df.to_sql(
                table_name,
                engine,
                if_exists="replace",
                index=False
            )

            all_tables.append(table_name)

            st.success(f"Table '{table_name}' uploaded successfully")

            st.subheader(f"Preview - {table_name}")

            st.dataframe(
                df.head(),
                use_container_width=True
            )

        except Exception as e:

            st.error(
                f"Error uploading {uploaded_file.name}"
            )

            st.write(str(e))

    # SHOW AVAILABLE TABLES
    st.subheader("Available Tables")

    st.write(all_tables)
# =========================
# SCHEMA EXTRACTION
# =========================

def get_schema(engine):

    schema = ""

    inspector = inspect(engine)

    tables = inspector.get_table_names()

    for table in tables:

        schema += f"\nTable: {table}\n"

        columns = inspector.get_columns(table)

        for column in columns:

            schema += f"{column['name']} ({column['type']})\n"

    return schema

    # GENERATE SCHEMA
    schema = get_schema(engine)

    # SHOW SCHEMA
    with st.expander("Database Schema"):

        st.code(schema)


# =========================
# USER INPUT
# =========================

user_question = st.text_area(
    "Ask anything in natural language"
)

# =========================
# SQL GENERATION
# =========================

SYSTEM_PROMPT = """
You are an expert SQL assistant.

Rules:
1. Generate ONLY SQL queries.
2. Use valid SQLite syntax.
3. Use ONLY available schema.
4. Support:
   - joins
   - subqueries
   - nested queries
   - CTEs
   - window functions
   - aggregations
   - insert/update/delete
   - create table
   - views
   - triggers
   - data cleaning
5. Never hallucinate columns.
6. Never explain.
7. Return executable SQL only.
"""

def generate_sql(question, schema):

    prompt = f"""
Generate ONLY SQL query.

STRICT RULES:
1. Return  executable SQL.
2. with explanatation explanation.
3. No markdown.
4. No comments.
5. Start directly with SELECT/UPDATE/etc.

DATABASE SCHEMA:
{schema}

QUESTION:
{question}
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
        {
            "role": "user",
            "content": prompt
        }
    ],
    temperature=0
)

    sql_query = response.choices[0].message.content.strip()

    sql_query = sql_query.replace("```sql", "")
    sql_query = sql_query.replace("```", "")

    keywords = [
        "SELECT",
        "UPDATE",
        "DELETE",
        "INSERT",
        "CREATE",
        "WITH"
    ]

    lines = sql_query.splitlines()

    clean_lines = []

    found_sql = False

    for line in lines:

        stripped = line.strip()

        upper = stripped.upper()

        if any(upper.startswith(k) for k in keywords):
            found_sql = True

        if found_sql:
            clean_lines.append(stripped)

    final_query = "\n".join(clean_lines)

    return final_query


# =========================
# SQL VALIDATION
# =========================

FORBIDDEN = [
    "DROP DATABASE",
    "TRUNCATE",
    "SHUTDOWN"
]

def validate_query(query):

    upper_query = query.upper()

    for keyword in FORBIDDEN:

        if keyword in upper_query:
            return False

    return True

# =========================
# EXECUTE SQL
# =========================

def execute_sql(query):

    try:

        with engine.connect() as conn:

            result = conn.execute(text(query))

            conn.commit()

            try:

                data = result.fetchall()

                columns = result.keys()

                df = pd.DataFrame(
                    data,
                    columns=columns
                )

                return {
                    "success": True,
                    "type": "table",
                    "data": df
                }

            except:

                return {
                    "success": True,
                    "type": "message",
                    "message": "Query executed successfully"
                }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }

# =========================
# QUERY RETRY AGENT
# =========================

def retry_query(question, schema, error):

    retry_prompt = f"""
Generate ONLY corrected SQL query.

STRICT RULES:
1. Return ONLY SQL.
2. with explanation.
3. No English text.
4. No markdown.
5. No comments.
6. Output should start directly with SELECT/UPDATE/etc.

DATABASE SCHEMA:
{schema}

QUESTION:
{question}

ERROR:
{error}
"""

    response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[
        {
            "role": "user",
            "content": retry_prompt
        }
    ],
    temperature=0
)

    fixed_query = response.choices[0].message.content.strip()

    # REMOVE MARKDOWN
    fixed_query = fixed_query.replace("```sql", "")
    fixed_query = fixed_query.replace("```", "")

    # EXTRACT ONLY SQL
    keywords = [
        "SELECT",
        "UPDATE",
        "DELETE",
        "INSERT",
        "CREATE",
        "WITH"
    ]

    lines = fixed_query.splitlines()

    clean_lines = []

    found_sql = False

    for line in lines:

        stripped = line.strip()

        upper = stripped.upper()

        if any(upper.startswith(k) for k in keywords):
            found_sql = True

        if found_sql:
            clean_lines.append(stripped)

    final_query = "\n".join(clean_lines)

    return final_query
if uploaded_files:
    schema = get_schema(engine)
else:
    schema = ""

# =========================
# MAIN EXECUTION
# =========================

if st.button("Generate & Execute SQL"):

    if user_question.strip() == "":

        st.warning("Please enter a question")

    else:

        with st.spinner("Generating SQL..."):

            sql_query = generate_sql(
                user_question,
                schema
            )

        st.subheader("Generated SQL")

        st.code(sql_query, language="sql")

        valid = validate_query(sql_query)

        if not valid:

            st.error("Unsafe query blocked")

        else:

            result = execute_sql(sql_query)

            # =========================
            # SUCCESS
            # =========================

            if result["success"]:

                if result["type"] == "table":

                    st.subheader("Query Result")

                    st.dataframe(
                        result["data"],
                        use_container_width=True
                    )

                else:

                    st.success(result["message"])

            # =========================
            # AUTO RETRY
            # =========================

            else:

                st.error("Query Failed")

                st.write(result["error"])

                st.warning("Trying to correct query automatically...")

                fixed_query = retry_query(
                    user_question,
                    schema,
                    result["error"]
                )

                st.subheader("Corrected SQL")

                st.code(fixed_query, language="sql")

                retry_result = execute_sql(fixed_query)

                if retry_result["success"]:

                    if retry_result["type"] == "table":

                        st.subheader("Corrected Query Result")

                        st.dataframe(
                            retry_result["data"],
                            use_container_width=True
                        )

                    else:

                        st.success(
                            retry_result["message"]
                        )

                else:

                    st.error("Correction Failed")

                    st.write(retry_result["error"])