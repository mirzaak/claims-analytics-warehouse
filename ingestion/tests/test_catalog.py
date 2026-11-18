import pytest

from claims_ingest.catalog import select_sources, sources_for_sample
from claims_ingest.errors import ConfigError


@pytest.mark.parametrize("sample", [1, 2])
def test_each_sample_has_eight_files_with_unique_tables(sample):
    sources = sources_for_sample(sample)

    assert len(sources) == 8
    assert len({source.table for source in sources}) == 8
    assert all(source.table.endswith(f"_s{sample:02d}") for source in sources)


def test_sample_1_uses_the_2010_beneficiary_link_published_by_cms():
    source = next(s for s in sources_for_sample(1) if s.key == "beneficiary_2010")

    assert source.filename == "de1_0_2010_beneficiary_summary_file_sample_20.zip"


def test_sample_2_uses_its_own_2010_beneficiary_file():
    source = next(s for s in sources_for_sample(2) if s.key == "beneficiary_2010")

    assert source.filename == "de1_0_2010_beneficiary_summary_file_sample_2.zip"


def test_unsupported_sample_is_rejected_with_the_valid_options():
    with pytest.raises(ConfigError, match="Supported samples: 1, 2"):
        sources_for_sample(3)


def test_only_filter_selects_one_source():
    sources = select_sources([1], ["inpatient_claims"])

    assert [source.table for source in sources] == ["inpatient_claims_s01"]


def test_unknown_source_is_rejected():
    with pytest.raises(ConfigError, match="Unknown source"):
        select_sources([1], ["dental_claims"])


def test_repeated_samples_are_processed_once():
    assert len(select_sources([1, 1])) == 8
