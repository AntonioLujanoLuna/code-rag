"""Tree-sitter node-type tables and grammar registry.

Grammars differ in the node-type names they use for the same concept, so these
sets enumerate the equivalents the chunker treats alike. Kept separate from the
chunker logic so the walking code stays readable.
"""

from __future__ import annotations

# Our language name (see domain.languages) -> (module, language-factory attribute).
# Each grammar ships its compiled parser in the wheel, so no runtime download.
GRAMMARS: dict[str, tuple[str, str]] = {
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "java": ("tree_sitter_java", "language"),
    "go": ("tree_sitter_go", "language"),
    "rust": ("tree_sitter_rust", "language"),
    "c": ("tree_sitter_c", "language"),
    "cpp": ("tree_sitter_cpp", "language"),
    "csharp": ("tree_sitter_c_sharp", "language"),
    "ruby": ("tree_sitter_ruby", "language"),
    "php": ("tree_sitter_php", "language_php"),
    "kotlin": ("tree_sitter_kotlin", "language"),
    "scala": ("tree_sitter_scala", "language"),
}

# Node types that denote a class-like container (children become its members).
CLASS_TYPES = {
    "class_declaration",
    "class_definition",
    "class_specifier",
    "class",
    "interface_declaration",
    "struct_specifier",
    "struct_declaration",
    "struct_item",
    "type_spec",
    "enum_declaration",
    "enum_item",
    "trait_item",
    "trait_declaration",
    "impl_item",
    "module",
    "mod_item",
    "record_declaration",
    "object_declaration",
}
# Node types that denote a function/method definition.
FUNCTION_TYPES = {
    "function_declaration",
    "function_definition",
    "function_item",
    "method_declaration",
    "method_definition",
    "method",
    "constructor_declaration",
}
CALL_TYPES = {
    "call_expression",
    "call",
    "method_invocation",
    "invocation_expression",
    "function_call_expression",
    "member_call_expression",
    "scoped_call_expression",
}
IMPORT_TYPES = {
    "import_statement",
    "import_declaration",
    "import_from_statement",
    "import_spec",
    "using_directive",
    "package_clause",
    "use_declaration",
    "namespace_use_declaration",
    "preproc_include",
}
DECORATOR_TYPES = {"decorator", "annotation", "marker_annotation", "attribute", "attribute_list"}
# Field/child types whose subtrees we don't descend into when resolving a name.
BODY_TYPES = {"block", "body", "compound_statement", "class_body", "declaration_list"}
