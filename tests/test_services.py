from backend.app.services import chunk_text, EmbeddingService

def test_chunking_preserves_text():
    text = "frase útil. " * 300
    chunks = chunk_text(text, size=100, overlap=20)
    assert len(chunks) > 2
    assert "frase útil" in chunks[0]

def test_embeddings_are_semantic_enough_for_local_retrieval():
    service = EmbeddingService()
    a = service.embed("eu gosto de música brasileira")
    b = service.embed("música brasileira é algo de que gosto")
    c = service.embed("o banco de dados usa vetores")
    assert service.similarity(a, b) > service.similarity(a, c)
