from importlib.metadata import version

import knowledge_automata


def test_package_version_matches_installed_metadata():
    assert knowledge_automata.__version__ == version("knowledge-automata")
