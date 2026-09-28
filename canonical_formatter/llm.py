import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

load_dotenv()


def get_llm(provider: str = "gemini", temperature: float = 0.2):
    """
    Central place to swap LLM providers without touching agent code.
    provider: 'gemini' (default) or 'groq' (fast fallback)
    """
    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model="gemini-3.5-flash-lite",
            google_api_key=os.getenv("GOOGLE_API_KEY"),
           
        )
    elif provider == "groq":
        return ChatGroq(
            model="openai/gpt-oss-120b",
            groq_api_key=os.getenv("GROQ_API_KEY"),
            temperature=temperature,
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")

def get_structured_llm(schema, temperature: float = 0.2):
    """
    Returns an LLM that outputs `schema`, using Gemini first and
    automatically falling back to Groq if Gemini errors (quota, outage, etc).
    """
    primary = get_llm("gemini", temperature).with_structured_output(schema)
    backup = get_llm("groq", temperature).with_structured_output(schema)
    return primary.with_fallbacks([backup])