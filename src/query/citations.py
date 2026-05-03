from src.models.schemas import Citation, SearchResult


def validate_citations(citations: list[Citation], results: list[SearchResult]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    result_ranges = {(result.repo_name, result.file_path): result for result in results}
    for citation in citations:
        result = result_ranges.get((citation.repo, citation.file))
        if result is None:
            errors.append(f"Citation {citation.repo}/{citation.file} was not retrieved.")
            continue
        if citation.start_line < result.start_line or citation.end_line > result.end_line:
            errors.append(
                f"Citation {citation.repo}/{citation.file}:{citation.start_line}-{citation.end_line} "
                "falls outside retrieved context."
            )
    return not errors, errors
