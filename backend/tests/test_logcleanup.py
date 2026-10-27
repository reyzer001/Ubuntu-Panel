from app.services import logcleanup


def test_trim_logs_keeps_only_tail(tmp_path):
    path = tmp_path / "backend.log"
    path.write_bytes(b"x" * 1000 + b"TAIL")

    result = logcleanup.trim_logs(
        roots=(tmp_path,),
        max_bytes=100,
        keep_bytes=4,
    )

    assert result["files"] == 1
    assert result["bytes_freed"] == 1000
    assert path.read_bytes() == b"TAIL"


def test_trim_logs_skips_small_files(tmp_path):
    path = tmp_path / "small.log"
    path.write_bytes(b"ok")

    result = logcleanup.trim_logs(
        roots=(tmp_path,),
        max_bytes=100,
        keep_bytes=4,
    )

    assert result["files"] == 0
    assert result["bytes_freed"] == 0
    assert path.read_bytes() == b"ok"
