import json
import os

from src.config.settings import get_settings
from src.models.schemas import SearchResult

# Module-level cache: last successful synthesis result for fallback
_last_result: str | None = None


class AnswerSynthesizer:
    def __init__(self) -> None:
        self.settings = get_settings()

    def synthesize(self, question: str, results: list[SearchResult]) -> str:
        global _last_result
        if not results:
            return (
                "I could not find indexed code that matches the question yet. "
                "Confirm ingestion so the backend can clone/fetch, parse, and index the code."
            )
        prompt = build_prompt(question, results)
        try:
            provider = self.settings.llm_provider.lower()
            if provider in ("google", "gemini"):
                answer = self._google(prompt)
            elif provider == "groq":
                answer = self._groq(prompt)
            else:
                answer = self._anthropic(prompt)
            _last_result = answer
            return answer
        except Exception:
            # Fallback: return cached last result if available, else extractive fallback
            if _last_result is not None:
                return _last_result
            return extractive_fallback(question, results)

    def _groq(self, prompt: str) -> str:
        from groq import Groq

        api_key = os.getenv("GROQ_API_KEY")
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model=self.settings.llm_model,
            temperature=0,
            max_tokens=1200,
        )
        return response.choices[0].message.content or ""

    def _anthropic(self, prompt: str) -> str:
        import anthropic

        client = anthropic.Anthropic()
        response = client.messages.create(
            model=self.settings.llm_model,
            max_tokens=1200,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        return "\n".join(block.text for block in response.content if getattr(block, "type", "") == "text").strip()

    def _google(self, prompt: str) -> str:
        from google import genai

        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=self.settings.llm_model, contents=prompt)
        return (response.text or "").strip()


def build_prompt(question: str, results: list[SearchResult]) -> str:
    context = []
    for index, result in enumerate(results[:8], start=1):
        context.append(
            {
                "id": index,
                "repo": result.repo_name,
                "file": result.file_path,
                "lines": f"{result.start_line}-{result.end_line}",
                "url": result.url,
                "summary": result.summary,
                "code": result.preview,
                "retrieval_method": ", ".join(result.retrieval_sources),
                "score": round(result.score, 4),
            }
        )
    return (
        "You are an expert code assistant. Answer the user's codebase question using ONLY the provided retrieved "
        "code context below. Do NOT invent files, functions, or behavior not present in the context.\n\n"
        "Rules:\n"
        "- Cite sources inline using [N] notation where N is the 'id' field.\n"
        "- Include the file path and line numbers in your citations.\n"
        "- If multiple sources agree, consolidate them.\n"
        "- Be concise and technical.\n\n"
        f"Question: {question}\n\n"
        f"Retrieved context (ranked by relevance):\n{json.dumps(context, indent=2)}\n\n"
        "Provide a thorough, technically accurate answer with inline [N] citations referencing the context IDs above."
    )


def extractive_fallback(question: str, results: list[SearchResult]) -> str:
    lines = [
        f"**Note:** LLM synthesis was temporarily unavailable. "
        f"Here are the top retrieved sources for: _{question}_\n"
    ]
    for i, result in enumerate(results[:5], start=1):
        source = f"`{result.repo_name}/{result.file_path}` lines {result.start_line}–{result.end_line}"
        lines.append(f"**[{i}]** {source}\n> {result.summary}\n")
    return "\n".join(lines)
