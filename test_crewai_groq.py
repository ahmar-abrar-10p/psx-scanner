from crewai import LLM
import os
os.environ["OPENAI_API_KEY"] = "NA"

try:
    llm = LLM(model="groq/llama-3.3-70b-versatile", api_key="test_key")
    print("CrewAI LLM init OK")
except Exception as e:
    print(f"Error: {e}")
