from fastapi import FastAPI, HTTPException, Body, UploadFile, File
from starlette.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import os, io
from dotenv import load_dotenv
import pandas as pd
import json
import re
import sys
from io import StringIO
from typing import List, Dict, Optional

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
global_data = []

class QueryRequest(BaseModel):
    prompt: str

class QueryResponse(BaseModel):
    response: Optional[dict] = None
    summary: str = None
    message: str = None

def generate_spec(prompt: str) -> dict:
    """
    Generate a Vega-Lite specification based on the user's request and the provided dataset.
    """
    bot_prompt = f"""
    You are a data visualization assistant responsible for generating Vega-Lite specifications. Vega-Lite is a high-level grammar of interactive graphics that produces JSON specifications for data visualizations.You are responsible for converting user requests into valid Vega-Lite specifications in JSON format, based on the dataset provided.
    Generate a Vega-Lite v5.21.0 JSON specification for the user prompt:"{prompt}". Additionally, 
    provide a one or two-sentence summary of the chart that will help the user understand the visualization.
    Provide your response in the following JSON format:
    {{
        "vega_lite_spec": [Your Vega-Lite specification here],
        "summary": [Your chart summary here]
    }}
    While generating the speculation, remember to strictly follow the format and make sure to double check for incorrections.
    Ensure the JSON response is properly formatted and parsable.
    """

    chat_completion = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": bot_prompt},
            {"role": "user", "content": prompt}
        ],
        response_format = {"type": "json_object"} 
    )
    vega_lite_spec = chat_completion.choices[0].message.content

    return vega_lite_spec

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

@app.post("/upload_data")
async def upload_data(file: UploadFile = File(...)):
    global schema, global_data
    schema = None
    if file.filename.endswith('.csv'):
        content = await file.read()
        df = pd.read_csv(io.StringIO(content.decode('utf-8')))
        global_data = df.to_dict(orient='records')
        schema = generate_schema(df)
        return {"message": "Data uploaded and schema generated successfully."}
    else:
        raise HTTPException(status_code=400, detail="Please upload a valid CSV file.")

def sanitize_input(code: str) -> str:
    code = re.sub(r"^(\s|)*(?i:python)?\s*", "", code)  # Clean start
    code = re.sub(r"(\s|)*$", "", code)  # Clean end
    code = re.sub(r"pd.read_csv\([^\)]+\)", "df", code)
    return code

def execute_code(code: str) -> str:
    df = pd.DataFrame(global_data)
    old_stdout = sys.stdout
    sys.stdout = mystdout = StringIO()
    try:
        cleaned_code = sanitize_input(code)
        exec_globals = {"df": df}
        exec(cleaned_code, exec_globals)
        sys.stdout = old_stdout
        return mystdout.getvalue()
    except Exception as e:
        sys.stdout = old_stdout
        return repr(e)

chat_generation_tool = {   
    "type": "function",
    "function": {
        "name": "generate_spec",
        "description": "Generate a Vega-Lite specification based on user questions about data visualization.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The generated prompt based on the dataset and user query."
                }
            },
            "required": ["prompt"],
        }
    }
}

data_analysis_tool = {
    "type": "function",
    "function": {
        "name": "execute_code",
        "type": "function",
        "description": "Execute provided Python code for data analysis and return the output. Please ensure to use print(...) for the output.",
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute."
                }
            },
            "required": ["code"]
        }
    }
}

tools = [chat_generation_tool, data_analysis_tool]

tool_map = {
    "generate_spec": generate_spec,
    "execute_code": execute_code
}

# print msg in red, accept multiple strings like print statement
def print_red(*strings):
    print("\033[91m" + " ".join(strings) + "\033[0m")


# print msg in blue, , accept multiple strings like print statement
def print_blue(*strings):
    print("\033[94m" + " ".join(strings) + "\033[0m")

def truncate_string(s: str, max_length: int = 100) -> str:
    """
    Truncate a string to a specified maximum length, appending '...' if truncated.
    
    :param s: The string to truncate.
    :param max_length: The maximum allowed length of the string.
    :return: The truncated string.
    """
    if len(s) > max_length:
        return s[:max_length] + '...'
    return s

@app.post("/query", response_model=QueryResponse)
async def query_openai(request: QueryRequest):
    df = pd.DataFrame(global_data)
    columns = df.columns.tolist()
    if not schema:
        return QueryResponse(message="Please upload a dataset before sending a message.")

    relevant, message = is_question_relevant(request.prompt, schema)

    if not relevant:
        return QueryResponse(message=message)

    system_prompt = """
    You are a helpful AI assistant. Use the tools provided below when necessary to answer the user's queries.
    The dataset is already loaded into a Pandas DataFrame called 'df'. The dataset's columns are: {columns}. 
    Remember: When dealing with all the columns except for MPG, make sure to capitalize the first letter of the column name!
    
    The tools you can utilize are:

    1. generate_spec: Generate a Vega-Lite JSON specification for the following request:"{request.prompt}". Additionally, 
    provide a one or two-sentence summary of the chart that will help the user understand the visualization.
    - Input: prompt

    2. execute_code: Executes Python code for data analysis. Ensure the code uses print(...) to output the results. 
    - The dataframe to be used is named 'df', which is already loaded with the dataset.
    - Input: code

    If the Vega-Lite specification is ill-formed and cannot be fixed, notify the user.
    Please format your response in the following JSON structure:
    {{
        "response": [Your Vega-Lite specification here or None],
        "summary": "[Your chart summary or data queries here]"
    }}
    If the response contains no vega-lite speculations, all the content will go into the "summary" field; if vega-lite speculations are present in the response,
    the speculation will be placed in the "response" field, and "summary" field should include a value-based analysis of the chart generated.
    Keep your answer in JSON format and NOT containing other information!
    Remember to call the appropriate tool based on the user's question and print outputs using print(...).
    """

    messages = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": request.prompt})

    i = 0
    max_iterations = 10
    while i < max_iterations:
        i += 1
        print("iteration:", i)
        response = client.chat.completions.create(
            model="gpt-4o-mini", temperature=0.0, messages=messages, tools=tools
        )
        if response.choices[0].message.content != None:
            print_red(response.choices[0].message.content)

        # if not function call
        if response.choices[0].message.tool_calls == None:
            break

        # if function call
        messages.append(response.choices[0].message)
        for tool_call in response.choices[0].message.tool_calls:
            print_blue("calling:", tool_call.function.name, "with", tool_call.function.arguments)
            # call the function
            arguments = json.loads(tool_call.function.arguments)
            function_to_call = tool_map[tool_call.function.name]
            result = function_to_call(**arguments)

            # create a message containing the result of the function call
            result_content = json.dumps({**arguments, "result": result})
            function_call_result_message = {
                "role": "tool",
                "content": result_content,
                "tool_call_id": tool_call.id,
            }
            print_blue("action result:", truncate_string(result_content))

            messages.append(function_call_result_message)
        if i == max_iterations and response.choices[0].message.tool_calls != None:
            print_red("Max iterations reached")
            return QueryResponse(message="The tool agent could not complete the task in the given time. Please try again.")
        
    assistant_message = response.choices[0].message.content
    if assistant_message:
        try:
            response_data = json.loads(assistant_message)
            vega_lite_spec = response_data.get('response')
            summary = response_data.get('summary')
            if vega_lite_spec:
                return QueryResponse(response=vega_lite_spec, summary=summary)
            return QueryResponse(message=response_data.get('summary'))
        except json.JSONDecodeError:
            return QueryResponse(message="Failed to parse the response.")
    else:
        return QueryResponse(message="The question is unanswerable from the assistant.")

# Root endpoint

app.mount("/static", StaticFiles(directory="client/build/static"), name="static")

@app.get("/")
async def serve_react_app():
    return FileResponse('client/build/index.html')

@app.get("/{path_name:path}")
async def serve_react_catchall(path_name: str):
    return FileResponse('client/build/index.html')