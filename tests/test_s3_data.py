"""S3 path for the data (`make data-up` → `dh.bootstrap.from_s3`), research-mode folders included. Fake S3, offline."""
import importlib.util
import shutil
import sys
import types

import pytest

from dh import bootstrap, data

STARTER = bootstrap.FILES
EXTRA = [f"products_cadusa/{f}" for f in bootstrap.EXTRA_FILES + bootstrap.EXTRA_OPTIONAL]
FUND = [f"fundamentals/{f}" for f in bootstrap.FUNDAMENTALS[1]]


@pytest.fixture
def fake_s3(tmp_path, monkeypatch):
    bucket = tmp_path / "bucket"

    class Client:
        def upload_file(self, src, b, key):
            (bucket / key).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, bucket / key)

        def download_file(self, b, key, dst):
            if not (bucket / key).exists():
                raise FileNotFoundError(key)
            shutil.copy(bucket / key, dst)

    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=lambda *a, **k: Client()))
    monkeypatch.setenv("S3_BUCKET", "team-bucket")
    return bucket


def _use(monkeypatch, folder, extra=()):
    monkeypatch.setattr(data, "load_config", lambda path=None: data.Config(data_dir=folder, extra=tuple(extra)))
    monkeypatch.setattr(bootstrap, "load_config", data.load_config)


def _fill(folder, paths):
    for p in paths:
        (folder / p).parent.mkdir(parents=True, exist_ok=True)
        (folder / p).write_text(f"x,{p}\n")


def _upload():
    spec = importlib.util.spec_from_file_location("upload_data", data.ROOT / "scripts" / "upload_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_upload_then_hosted_copy_gets_the_research_folders(fake_s3, tmp_path, monkeypatch):
    laptop, host = tmp_path / "laptop", tmp_path / "host"
    _fill(laptop, list(STARTER) + EXTRA + FUND)
    _use(monkeypatch, laptop, ("cadusa",))
    up = _upload()
    assert set(up.files_to_upload(laptop)) == set(STARTER) | set(EXTRA) | set(FUND)
    assert up.main() == 0
    assert (fake_s3 / "raw" / "products_cadusa" / "prices_daily.csv").exists()
    _use(monkeypatch, host, ("cadusa",))
    assert not bootstrap.data_present()
    assert bootstrap.from_s3() == ""
    assert bootstrap.data_present() and (host / "fundamentals" / "annual.csv").read_text() == "x,fundamentals/annual.csv\n"


def test_demo_needs_and_fetches_only_the_starter(fake_s3, tmp_path, monkeypatch):
    laptop, host = tmp_path / "laptop", tmp_path / "host"
    _fill(laptop, list(STARTER) + EXTRA + FUND)
    _use(monkeypatch, laptop)
    assert _upload().main() == 0
    _use(monkeypatch, host)                                    # extra = []: the demo
    assert bootstrap.required() == list(STARTER)
    assert bootstrap.from_s3() == "" and bootstrap.data_present()
    assert not (host / "products_cadusa").exists() and not (host / "fundamentals").exists()


def test_missing_extra_catalogue_in_s3_is_reported(fake_s3, tmp_path, monkeypatch):
    laptop, host = tmp_path / "laptop", tmp_path / "host"
    _fill(laptop, STARTER)
    _use(monkeypatch, laptop)
    assert _upload().main() == 0
    _use(monkeypatch, host, ("cadusa",))
    assert "S3 unavailable" in bootstrap.from_s3() and not bootstrap.data_present()
