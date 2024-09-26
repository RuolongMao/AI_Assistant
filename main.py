from fastapi import FastAPI, HTTPException, Body, UploadFile, File
from starlette.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import os
from dotenv import load_dotenv
import pandas as pd
import json

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to restrict allowed origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
)

schema = None

class QueryRequest(BaseModel):
    prompt: str

class QueryResponse(BaseModel):
    response: dict = None
    summary: str = None
    message: str = None

@app.post("/upload_data")
async def upload_data(file: UploadFile = File(...)):
    global schema
    schema = None
    if file.filename.endswith('.csv'):
        content = await file.read()
        from io import BytesIO
        df = pd.read_csv(BytesIO(content))
        schema = generate_schema(df)
        return {"message": "Data uploaded and schema generated successfully."}
    else:
        raise HTTPException(status_code=400, detail="Please upload a valid CSV file.")

def generate_schema(df):
    schema = []
    for col in df.columns:
        sample_values = df[col].dropna().unique()[:5].tolist()
        data_type = infer_data_type(df[col])
        schema.append({
            'name': col,
            'type': data_type,
            'sampleValues': sample_values
        })
    return schema

def infer_data_type(series):
    if pd.api.types.is_numeric_dtype(series):
        return 'quantitative'
    elif pd.api.types.is_datetime64_any_dtype(series):
        return 'temporal'
    else:
        return 'nominal'

def is_question_relevant(question, schema):
    schema_description = "\n".join([
        f"{col['name']}: {col['type']}"
        for col in schema
    ])

    prompt = f"""
You are an AI assistant that determines whether a user's question is relevant to a dataset.

Dataset Schema:
{schema_description}

Question:
"{question}"

First, determine if the question is relevant to the dataset. If it is, answer "yes". If not, answer "no".

If the answer is "no", provide a response in the following JSON format:

{{
    "relevance": "no",
    "message": "The question \\"{question}\\" is not relevant to the dataset, which [provide a brief description of the dataset based on the schema]. It does not pertain to any data analysis or visualization task."
}}

If the answer is "yes", simply respond with:

{{
    "relevance": "yes"
}}

Important:

- Ensure that the JSON response is properly formatted.
- Do not include any additional text outside the JSON response.
- The dataset description should be concise and based on the dataset schema provided.
"""

    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="gpt-3.5-turbo",
        )
        assistant_message = response.choices[0].message.content.strip()

        response_data = json.loads(assistant_message)

        if response_data.get('relevance') == 'yes':
            return True, None
        else:
            return False, response_data.get('message')

    except Exception as e:
        return False, "An error occurred while checking question relevance."

@app.post("/query", response_model=QueryResponse)
async def query_openai(request: QueryRequest):
    try:
        if not schema:
            return QueryResponse(message="Please upload a dataset before sending a message.")

        relevant, message = is_question_relevant(request.prompt, schema)

        if not relevant:
            return QueryResponse(message=message)

        schema_description = "\n".join([
            f"{col['name']}: {col['type']}, samples: {col['sampleValues']}"
            for col in schema
        ])

        prompt = f"""
You are a data visualization assistant. The user will provide a query about a dataset.

Dataset Schema:
{schema_description}

The full dataset is available and will be supplied at rendering time. Do not include the data inline in the Vega-Lite specification.

Generate a Vega-Lite JSON specification for the following request:
"{request.prompt}"

Additionally, provide a one or two-sentence summary of the chart that will help the user understand the visualization.

Provide your response in the following JSON format:
{{
    "vega_lite_spec": [Your Vega-Lite specification here],
    "summary": [Your chart summary here]
}}

Ensure the JSON response is properly formatted and parsable.
"""

        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            model="gpt-3.5-turbo",
        )

        assistant_message = chat_completion.choices[0].message.content

        try:
            response_data = json.loads(assistant_message)
            vega_lite_spec = response_data.get('vega_lite_spec')
            summary = response_data.get('summary')

            if vega_lite_spec:
                vega_lite_spec['data'] = {"name": "data"}

            return QueryResponse(response=vega_lite_spec, summary=summary)
        except json.JSONDecodeError:
            return QueryResponse(message="Failed to parse the assistant's response.")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Root endpoint

app.mount("/static", StaticFiles(directory="client/build/static"), name="static")

@app.get("/")
async def serve_react_app():
    return FileResponse('client/build/index.html')

@app.get("/{path_name:path}")
async def serve_react_catchall(path_name: str):
    return FileResponse('client/build/index.html')
