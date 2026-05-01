import hashlib
import re
from typing import List, Dict, Any, Optional
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript

class CodeParser:
    """
    AST-aware code parser for extracting logical chunks (functions/classes)
    and generating stable hashes for incremental indexing.
    """
    
    def __init__(self):
        # Initialize languages using the 2026 standardized bindings
        self.languages = {
            "python": Language(tspython.language()),
            "javascript": Language(tsjavascript.language()),
        }
        self.parser = Parser()

    def get_chunks(self, code: str, language_name: str) -> List[Dict[str, Any]]:
        """
        Parses code and returns a list of chunks based on AST nodes.
        """
        from tree_sitter import Query
        
        if language_name not in self.languages:
            return [{
                "type": "file", 
                "content": code, 
                "start_line": 1, 
                "end_line": len(code.splitlines()),
                "hash": self.compute_ast_hash(code)
            }]
        
        lang = self.languages[language_name]
        self.parser.language = lang
        
        tree = self.parser.parse(bytes(code, "utf8"))
        
        # Language-specific queries to avoid "Invalid node type" errors
        queries = {
            "python": "(function_definition) @func (class_definition) @class",
            "javascript": "(function_declaration) @func (class_definition) @class (method_definition) @method"
        }
        
        query_scm = queries.get(language_name, "(function_definition) @func")
        query = Query(lang, query_scm)
        
        from tree_sitter import QueryCursor
        cursor = QueryCursor(query)
        captures = cursor.captures(tree.root_node)
        
        chunks = []
        for tag, nodes in captures.items():
            for node in nodes:
                content = code[node.start_byte:node.end_byte]
                chunks.append({
                    "type": tag,
                    "content": content,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "hash": self.compute_ast_hash(content)
                })
            
        # If no logical chunks were found (e.g. script-style file), return the whole file
        if not chunks:
            chunks.append({
                "type": "file",
                "content": code,
                "start_line": 1,
                "end_line": len(code.splitlines()),
                "hash": self.compute_ast_hash(code)
            })
            
        return chunks

    def compute_ast_hash(self, code: str) -> str:
        """
        Computes a hash of the code after stripping comments and extra whitespace.
        This ensures that formatting-only changes don't trigger re-indexing.
        """
        # 1. Remove comments (Simple regex-based approach for initial version)
        code = re.sub(r'#.*', '', code)
        code = re.sub(r'//.*', '', code)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        
        # 2. Normalize whitespace (remove all tabs, newlines, and spaces)
        normalized = "".join(code.split())
        
        # 3. Hash the logical content
        return hashlib.sha256(normalized.encode()).hexdigest()

if __name__ == "__main__":
    # Intern Smoke Test
    parser = CodeParser()
    sample_py = """
def calculate_sum(a, b):
    # This is a comment that should not affect the hash
    return a + b

class MathTool:
    def multiply(self, x, y):
        return x * y
"""
    chunks = parser.get_chunks(sample_py, 'python')
    print(f"Extracted {len(chunks)} chunks from Python sample.")
    for c in chunks:
        print(f" - [{c['type']}] Lines {c['start_line']}-{c['end_line']} | Hash: {c['hash'][:8]}")
