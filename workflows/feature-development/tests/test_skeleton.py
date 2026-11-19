from pathlib import Path


def test_workflow_package_has_readme():
    assert (Path(__file__).parent.parent / "README.md").is_file()
