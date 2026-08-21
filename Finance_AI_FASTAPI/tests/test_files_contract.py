import asyncio

from app.data_gateway.repositories.files import get_owned_ready_files


class CapturingPool:
    def __init__(self):
        self.query = ""
        self.args = ()

    async def fetch(self, query, *args):
        self.query = query
        self.args = args
        return [
            {
                "file_id": "file_1",
                "filename": "requirement.md",
                "content_type": "text/markdown",
                "extension": ".md",
                "size_bytes": 10,
                "storage_path": "data/uploads/file_1.md",
            }
        ]


def test_owned_files_require_ready_and_unexpired_records():
    pool = CapturingPool()
    result = asyncio.run(
        get_owned_ready_files(
            pool,
            user_id="user-1",
            file_ids=["file_1"],
        )
    )

    assert [item["file_id"] for item in result] == ["file_1"]
    assert "status='ready'" in pool.query
    assert "expires_at > NOW()" in pool.query
    assert pool.args == ("user-1", ["file_1"])
