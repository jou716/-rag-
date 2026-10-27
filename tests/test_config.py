import pytest

from app.config import settings


@pytest.mark.skipif(
    not settings.source_doc_path.is_file(),
    reason="source DOCX is not included in the public repository",
)
def test_source_document_exists() -> None:
    assert settings.source_doc_path.exists()


def test_database_target_does_not_contain_password() -> None:
    if settings.mysql_password:
        assert settings.mysql_password not in settings.mysql_target
    else:
        assert "@" in settings.mysql_target
