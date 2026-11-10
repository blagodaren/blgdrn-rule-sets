import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "manage_rules.py"
SPEC = importlib.util.spec_from_file_location("manage_rules", MODULE)
rules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rules)


class BuildSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "ruleset").mkdir()
        (self.root / "sources" / "static").mkdir(parents=True)

    def setup_manifest(self, entries):
        (self.root / "sources.json").write_text(json.dumps({"version": 1, "sources": entries}), encoding="utf-8")
        providers = {}
        for number, entry in enumerate(entries):
            providers[str(number)] = {
                "type": "http", "behavior": entry["behavior"], "format": entry["format"],
                "url": rules.REPOSITORY_BASE + entry["output"], "path": "./" + entry["output"],
            }
        (self.root / "rule-providers.yaml").write_text(yaml.safe_dump({"rule-providers": providers}), encoding="utf-8")

    def static(self, name="local"):
        return {"output": f"ruleset/{name}.yaml", "behavior": "classical", "format": "yaml",
                "mode": "static", "source": f"sources/static/{name}.yaml"}

    def mirror(self):
        return {"output": "ruleset/remote.yaml", "behavior": "classical", "format": "yaml",
                "mode": "mirror", "url": "https://example.com/remote.yaml"}

    def write(self, path, text):
        (self.root / path).write_text(text, encoding="utf-8")

    def test_offline_build_never_downloads_mirrors(self):
        local, remote = self.static(), self.mirror()
        self.setup_manifest([local, remote])
        self.write(local["source"], "payload:\n  - DOMAIN,local.example\n")
        original = "payload:\n  - DOMAIN,remote.example\n"
        self.write(remote["output"], original)
        with patch.object(rules, "download", side_effect=AssertionError("network access")) as download:
            rules.build(self.root, Path("unused"))
            download.assert_not_called()
        self.assertEqual((self.root / remote["output"]).read_text(), original)
        self.assertEqual((self.root / local["output"]).read_bytes(), (self.root / local["source"]).read_bytes())

    def test_bad_download_preserves_all_existing_outputs(self):
        local, remote = self.static(), self.mirror()
        self.setup_manifest([local, remote])
        original = "payload:\n  - DOMAIN,old.example\n"
        for entry in (local, remote):
            self.write(entry["output"], original)
        self.write(local["source"], "payload:\n  - DOMAIN,new.example\n")
        def bad_download(url, target):
            target.write_text("<html>upstream error</html>", encoding="utf-8")
        with patch.object(rules, "download", side_effect=bad_download):
            with self.assertRaises(ValueError):
                rules.build(self.root, Path("unused"), refresh=True)
        for entry in (local, remote):
            self.assertEqual((self.root / entry["output"]).read_text(), original)

    def test_refresh_cannot_download_static_source(self):
        entry = self.static()
        self.setup_manifest([entry])
        self.write(entry["source"], "payload:\n  - DOMAIN,local.example\n")
        with patch.object(rules, "download", side_effect=AssertionError("network access")) as download:
            rules.build(self.root, Path("unused"), refresh=True)
            download.assert_not_called()

    def test_retired_upstream_is_rejected_in_manifest(self):
        entry = self.mirror()
        entry["url"] = "https://ssc.magickvn.com/mrs/file.mrs"
        self.setup_manifest([entry])
        with self.assertRaisesRegex(ValueError, "Retired upstream"):
            rules.load_manifest(self.root)

    def test_static_download_url_is_rejected(self):
        entry = self.static()
        entry["url"] = "https://example.com/file"
        self.setup_manifest([entry])
        with self.assertRaisesRegex(ValueError, "cannot have a download URL"):
            rules.load_manifest(self.root)

    def test_retired_upstream_redirect_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "retired upstream"):
            rules.UpstreamRedirectHandler().redirect_request(
                None, None, 302, "", {}, "https://ssc.magickvn.com/file")

    def test_payload_type_and_malformed_rules_are_rejected(self):
        path = self.root / "ruleset" / "test.yaml"
        for value in ("payload: bad", "payload: []", "payload: [123]",
                      "payload: [DOMAIN]", "payload: ['IP-CIDR,999.0.0.0/8']"):
            with self.subTest(value=value):
                path.write_text(value, encoding="utf-8")
                with self.assertRaises(ValueError):
                    rules.validate_yaml(path)

    def test_invalid_static_rows_fail_before_conversion(self):
        path = self.root / "sources" / "static" / "test.list"
        for behavior, value in (("domain", "https://example.com"),
                                ("domain", "DOMAIN,example.com"),
                                ("domain", "+..example.com"),
                                ("domain", "foo*bar.example"),
                                ("ipcidr", "192.0.2.1/24"),
                                ("ipcidr", "not-an-ip")):
            with self.subTest(value=value):
                path.write_text(value, encoding="utf-8")
                with self.assertRaises(ValueError):
                    rules.text_rules(path, behavior)

    def test_converter_cannot_silently_skip_invalid_rows(self):
        result = subprocess.CompletedProcess([], 0, 'warning: skip invalid domain from rule provider', '')
        with patch.object(rules.subprocess, "run", return_value=result):
            with self.assertRaisesRegex(ValueError, "skipped invalid rules"):
                rules.convert(Path("mihomo"), "domain", "text", Path("source"), Path("target"))

    def test_legacy_literal_allowlist_is_exact_and_does_not_expand_grammar(self):
        path = self.root / "sources" / "static" / "legacy.list"
        allowed = ["domain-keyword,anidub"]
        path.write_text("domain-keyword,anidub\n+.example.com\n", encoding="utf-8")
        self.assertEqual(rules.text_rules(path, "domain", allowed), allowed + ["+.example.com"])
        for invalid in ("domain-keyword,other", "DOMAIN,example.com", "DOMAIN-KEYWORD,anidub"):
            with self.subTest(invalid=invalid):
                path.write_text(invalid + "\n", encoding="utf-8")
                with self.assertRaises(ValueError):
                    rules.text_rules(path, "domain", allowed)
        path.write_text(allowed[0] + "\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            rules.text_rules(path, "domain")

    def test_legacy_literal_allowlist_only_applies_to_static_domain_mrs(self):
        for entry in (self.static(), self.mirror()):
            entry["legacy_literal_domains"] = ["domain-keyword,anidub"]
            self.setup_manifest([entry])
            with self.assertRaisesRegex(ValueError, "require a static domain MRS"):
                rules.load_manifest(self.root)
        entry = {"output": "ruleset/legacy.mrs", "behavior": "domain", "format": "mrs",
                 "mode": "static", "source": "sources/static/legacy.list",
                 "legacy_literal_domains": ["domain-keyword,anidub"]}
        self.setup_manifest([entry])
        self.assertEqual(rules.load_manifest(self.root), [entry])

    def test_legacy_literal_is_accepted_during_build_and_output_validation(self):
        entry = {"output": "ruleset/legacy.mrs", "behavior": "domain", "format": "mrs",
                 "mode": "static", "source": "sources/static/legacy.list",
                 "legacy_literal_domains": ["domain-keyword,anidub"]}
        self.write(entry["source"], "domain-keyword,anidub\n")
        target = self.root / entry["output"]
        def copy_converter(mihomo, behavior, format_, source, destination):
            destination.write_bytes(source.read_bytes())
        with patch.object(rules, "convert", side_effect=copy_converter):
            rules.static_output(entry, self.root, target, Path("unused"))
            self.assertEqual(rules.validate_output(entry, target, Path("unused"), self.root), 1)
        self.assertEqual(target.read_bytes(), (self.root / entry["source"]).read_bytes())

    def test_provider_behavior_mismatch_is_rejected(self):
        entry = self.static()
        self.setup_manifest([entry])
        path = self.root / "rule-providers.yaml"
        path.write_text(path.read_text().replace("classical", "domain"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "behavior/format"):
            rules.validate_providers(self.root, [entry])

    def test_path_escape_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsafe path"):
            rules.safe_path(self.root, "ruleset/../../elsewhere.yaml", "ruleset")


if __name__ == "__main__":
    unittest.main()
