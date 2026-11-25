from conftest import NOW, beneficiary_rows, cache_source, make_source, read_prepared

from claims_ingest.pipeline import export_sources


def test_export_writes_one_current_file_per_table(settings, tmp_path):
    source = make_source()
    cache_source(settings, source, beneficiary_rows(3))
    out = tmp_path / "export"

    exported = export_sources([source], settings, out, clock=lambda: NOW)

    files = list((out / source.table).glob("*.csv.gz"))
    assert files == [exported[0].path]
    assert len(read_prepared(files[0])) == 3


def test_export_replaces_the_previous_batch_file(settings, tmp_path):
    source = make_source()
    out = tmp_path / "export"
    cache_source(settings, source, beneficiary_rows(3))
    first = export_sources([source], settings, out, clock=lambda: NOW)[0].path

    cache_source(settings, source, beneficiary_rows(2))
    second = export_sources([source], settings, out, clock=lambda: NOW)[0].path

    assert first != second
    assert list((out / source.table).glob("*.csv.gz")) == [second]
