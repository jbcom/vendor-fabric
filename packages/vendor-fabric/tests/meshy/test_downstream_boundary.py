from pathlib import Path


def test_text_to_image_runtime_uses_shared_base_transport_only() -> None:
    meshy_root = Path(__file__).parents[2] / "src" / "vendor_fabric" / "meshy"
    source = (meshy_root / "text2image.py").read_text()
    connector_source = (meshy_root / "connector.py").read_text()
    assert "from vendor_fabric.meshy import base" in source
    assert "requester or base.request" in source
    assert "base.poll_task" in source
    assert "requester=self._meshy_request" in connector_source
    assert '@capability(\n        "generate_image",' in connector_source
    assert "httpx.request" not in source
    assert "requests." not in source
    assert "MESHY_API_KEY" not in source


def test_image_job_delegates_download_to_shared_base() -> None:
    meshy_root = Path(__file__).parents[2] / "src" / "vendor_fabric" / "meshy"
    source = (meshy_root / "jobs.py").read_text()
    assert "text2image.create(" in source
    assert "text2image.poll(" in source
    assert "text2image.download_first(" in source
