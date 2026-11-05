import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import export_snv_q15_typed_local_graph as g

S48_NODE = Path('/workspace/ivanka-lab/snv-q15-original-verification-20261105/S48-unique-parent-q15.json')
S48_LINK = Path('/workspace/ivanka-lab/snv-q15-direct-links-20261105/S48-conservative-direct-Q15.json')
S12_NODE = Path('/workspace/ivanka-lab/snv-q15-original-verification-20261105/S12-unique-parent-q15.json')
S12_LINK = Path('/workspace/ivanka-lab/snv-q15-direct-links-20261105/S12-conservative-direct-Q15.json')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def graph_from(node, link, sample='S'):
    return g.build_typed_local_graph(
        sample=sample,
        node_report=copy.deepcopy(node),
        link_report=copy.deepcopy(link),
        node_report_sha256='n' * 64,
        link_report_sha256='l' * 64,
    )


class SNVQ15TypedLocalGraphTests(unittest.TestCase):
    @unittest.skipUnless(
        all(p.is_file() for p in (S48_NODE, S48_LINK, S12_NODE, S12_LINK)),
        "Private source-pinned original S48/S12 reports not available in CI")
    def test_s48_real_frozen_reports_produce_two_direct_alt_ref_links_and_withhold_217_677(self):
        graph = graph_from(load(S48_NODE), load(S48_LINK), sample='73090AMIDI-MidHCV_S48')
        self.assertEqual(graph['schema_version'], g.GRAPH_SCHEMA)
        self.assertEqual(graph['source_reports']['source_sha256'], load(S48_NODE)['source_sha256'])
        self.assertFalse(graph['safety']['affects_198_acceptance'])
        self.assertFalse(graph['safety']['transitive_inference_used'])
        self.assertFalse(graph['safety']['full_length_haplotype_phase_claimed'])
        self.assertFalse(graph['safety']['independent_physical_molecules_claimed'])
        self.assertFalse(graph['safety']['fabricated_full_length_sequences'])
        supported = [e for e in graph['edges'] if e['direct_local_link_supported']]
        self.assertEqual(len(supported), 2)
        self.assertEqual(len(graph['edges']), 2,
                         "Withheld alleles must never be presented as graph edges")
        combos = {(e['candidate_sites'][0].split('::')[-1], e['candidate_sites'][1].split('::')[-1], e['allele_combination']) for e in supported}
        self.assertIn(('A>G', 'T>C', 'alternative_reference'), combos)
        self.assertIn(('C>T', 'T>C', 'alternative_reference'), combos)
        ev217 = [e for e in supported if 'pos217' in e['from'] and 'pos677' in e['to'] or 'pos217' in e['to'] and 'pos677' in e['from']]
        self.assertEqual(ev217, [])
        withheld217677 = [e for e in graph['negative_unknown']
                          if 'pos217::A>G' in e.get('from','') + e.get('to','')
                          and 'pos677::C>T' in e.get('from','') + e.get('to','')
                          and e['allele_combination'] == 'alternative_alternative']
        self.assertTrue(withheld217677)
        self.assertEqual(withheld217677[0]['kind'], 'insufficient_direct_support')
        self.assertEqual(withheld217677[0]['observed_joint_original_pair_ids'], 1)
        for e in graph['edges']:
            self.assertTrue(e['same_original_r1_r2_pair_required'])
            self.assertTrue(e['q15_required_all_31_bases'])
            self.assertFalse(e['transitive_link_imputed'])
            self.assertFalse(e['haplotype_phase_inferred'])
            self.assertFalse(e['fabricated_full_length_sequence'])
            self.assertFalse(e['raw_qnames_disclosed'])
            self.assertNotIn('qname_id', json.dumps(e).lower())
        self.assertTrue(any(u['kind'] == 'reference_reference_coobservation_not_variant_link' for u in graph['negative_unknown']))

    @unittest.skipUnless(
        all(p.is_file() for p in (S48_NODE, S48_LINK, S12_NODE, S12_LINK)),
        "Private source-pinned original S48/S12 reports not available in CI")
    def test_s12_real_frozen_reports_have_zero_accepted_edges_with_unqualified_344_394(self):
        node = load(S12_NODE)
        link = load(S12_LINK)
        self.assertEqual([(c['snv_offset_zero_based'], c['candidate_meets_local_q15_screen']) for c in node['candidates']],
                         [(344, False), (394, False), (458, True)])
        graph = graph_from(node, link, sample='73111AMIDI-MidHCV_S12')
        supported = [e for e in graph['edges'] if e['direct_local_link_supported']]
        self.assertEqual(supported, [])
        self.assertEqual(graph['edges'], [],
                         "Unqualified S12 nodes cannot have graph edges")
        self.assertEqual(len(graph["nodes"]), 1,
                         "Unqualified S12 candidate sites are diagnostics, not graph nodes")
        self.assertTrue(all(n["candidate_meets_local_q15_screen"]
                            for n in graph["nodes"] if n["type"] == "snv_q15_candidate_site"))
        withheld = [e for e in graph['negative_unknown'] if e['kind'] == 'withheld_for_unqualified_node']
        self.assertTrue(withheld)
        self.assertTrue(any(u['kind'] == 'unqualified_snv_candidate_withheld' and 'pos344' in u['candidate_node']
                            for u in graph['negative_unknown']))
        self.assertTrue(any(u['kind'] == 'unqualified_snv_candidate_withheld' and 'pos394' in u['candidate_node']
                            for u in graph['negative_unknown']))

    def _synthetic_reports(self):
        node = {
            'schema_version': g.NODE_SCHEMA,
            'source_sha256': {k: '1' * 64 for k in g.REQUIRED_NODE_SOURCE_KEYS},
            'pairs_scanned': 100,
            'q15_minimum_base_quality': 15,
            'observed_pair_threshold': 10,
            'research_only': True,
            'reported_local_snv_candidates': 3,
            'candidates': [
                dict(parent_fasta_index=1, snv_offset_zero_based=10, baseline_base='A', alternate_base='C',
                     candidate_meets_local_q15_screen=True,
                     q15_original_pairs_observing_alternative=20,
                     q15_distinct_consistent_paired_sequences_alternative=20,
                     q15_original_pairs_observing_reference=30,
                     q15_original_pairs_with_both_alleles=0,
                     q15_original_pairs_without_exact_31mer=50),
                dict(parent_fasta_index=1, snv_offset_zero_based=20, baseline_base='G', alternate_base='T',
                     candidate_meets_local_q15_screen=True,
                     q15_original_pairs_observing_alternative=20,
                     q15_distinct_consistent_paired_sequences_alternative=20,
                     q15_original_pairs_observing_reference=30,
                     q15_original_pairs_with_both_alleles=0,
                     q15_original_pairs_without_exact_31mer=50),
                dict(parent_fasta_index=1, snv_offset_zero_based=30, baseline_base='T', alternate_base='A',
                     candidate_meets_local_q15_screen=True,
                     q15_original_pairs_observing_alternative=20,
                     q15_distinct_consistent_paired_sequences_alternative=20,
                     q15_original_pairs_observing_reference=30,
                     q15_original_pairs_with_both_alleles=0,
                     q15_original_pairs_without_exact_31mer=50),
            ],
            'original_pair_ids_are_independent_physical_molecules': False,
            'full_length_haplotype_phase_inferred': False,
            'per_haplotype_read_depth_assigned': False,
            'modifies_micall_final_max': False,
            'changes_198_sample_acceptance': False,
        }
        qualified = [{k: c[k] for k in ('parent_fasta_index', 'snv_offset_zero_based', 'baseline_base', 'alternate_base', 'candidate_meets_local_q15_screen')} for c in node['candidates']]
        def ev(ab=12, ar=0, ra=0, rr=0, supported=None):
            obs = {'reference_reference': rr, 'alternative_reference': ar, 'reference_alternative': ra, 'alternative_alternative': ab}
            sig = dict(obs)
            sup = [] if supported is None else supported
            return {
                'observed_joint_original_pair_ids': obs,
                'observed_joint_distinct_consistent_pair_sequences': sig,
                'supported_direct_local_allele_combinations': sup,
                'direct_local_link_supported': bool(sup),
                'withheld_for_unqualified_node': False,
                'transitive_link_imputed': False,
                'haplotype_phase_inferred': False,
                'joint_pair_counts_are_independent_physical_molecules': False,
            }
        link = {
            'schema_version': g.LINK_SCHEMA,
            'source_sha256': dict(node['source_sha256']),
            'original_pairs_scanned': 100,
            'minimum_direct_original_pair_ids_and_signatures': 10,
            'minimum_phred_all_31_bases': 15,
            'qualified_unphased_nodes': qualified,
            'candidate_pair_count': 3,
            'direct_allele_link_evidence': [
                dict(candidate_indices_zero_based=[0, 1], **ev(ab=12, supported=['alternative_alternative'])),
                dict(candidate_indices_zero_based=[1, 2], **ev(ab=12, supported=['alternative_alternative'])),
                dict(candidate_indices_zero_based=[0, 2], **ev(ab=0, rr=12, supported=[])),
            ],
            'original_pair_ids_are_independent_physical_molecules': False,
            'full_length_haplotype_phase_inferred': False,
            'per_haplotype_coverage_assigned': False,
            'transitive_links_created': False,
            'modifies_micall_final_max': False,
            'changes_198_acceptance': False,
        }
        return node, link

    def test_synthetic_ab_bc_never_create_transitive_ac(self):
        node, link = self._synthetic_reports()
        graph = graph_from(node, link)
        supported = [e for e in graph['edges'] if e['direct_local_link_supported']]
        sites = [tuple(sorted([e['from'].split('::pos')[1].split('::')[0], e['to'].split('::pos')[1].split('::')[0]])) for e in supported]
        self.assertEqual(sorted(sites), [('10', '20'), ('20', '30')])
        ac = [e for e in supported if 'pos10::' in e['from'] + e['to'] and 'pos30::' in e['from'] + e['to']]
        self.assertEqual(ac, [])
        self.assertFalse(any(e.get('transitive_inference_used') for e in graph['edges']))

    def test_duplicate_pair_records_and_absent_pairs_fail_closed(self):
        node, link = self._synthetic_reports()
        link["direct_allele_link_evidence"][2]["candidate_indices_zero_based"] = [0, 1]
        with self.assertRaisesRegex(g.GraphBuildError, "repeated or missing"):
            graph_from(node, link)
        node, link = self._synthetic_reports()
        link["direct_allele_link_evidence"][2]["candidate_indices_zero_based"] = [0, 3]
        with self.assertRaisesRegex(g.GraphBuildError, "outside node count"):
            graph_from(node, link)

    def test_mismatched_source_read_count_q15_floor_and_signature_counts_fail(self):
        node, link = self._synthetic_reports()
        link["original_pairs_scanned"] += 1
        with self.assertRaisesRegex(g.GraphBuildError, "pair scan count"):
            graph_from(node, link)
        node, link = self._synthetic_reports()
        link["minimum_phred_all_31_bases"] += 1
        with self.assertRaisesRegex(g.GraphBuildError, "quality floor"):
            graph_from(node, link)
        node, link = self._synthetic_reports()
        e = link["direct_allele_link_evidence"][0]
        e["observed_joint_distinct_consistent_pair_sequences"]["alternative_alternative"] += 1
        e["observed_joint_original_pair_ids"]["alternative_alternative"] = 0
        with self.assertRaisesRegex(g.GraphBuildError, "more signatures"):
            graph_from(node, link)

    def test_forged_qualification_must_match_node_report(self):
        node, link = self._synthetic_reports()
        link["direct_allele_link_evidence"][0]["withheld_for_unqualified_node"] = True
        with self.assertRaisesRegex(g.GraphBuildError, "qualification disagrees"):
            graph_from(node, link)

    def test_only_real_supported_allele_nodes_and_edges_present(self):
        node, link = self._synthetic_reports()
        edge = link["direct_allele_link_evidence"][0]
        edge["observed_joint_original_pair_ids"]["alternative_alternative"] = 0
        edge["observed_joint_distinct_consistent_pair_sequences"]["alternative_alternative"] = 0
        edge["supported_direct_local_allele_combinations"] = []
        edge["direct_local_link_supported"] = False
        graph = graph_from(node, link)
        self.assertEqual(len(graph["edges"]), 1)
        self.assertTrue(all(e["direct_local_link_supported"] for e in graph["edges"]))
        self.assertFalse(any("pos10::" in n["id"] and
                             n["type"] == "snv_q15_observed_allele_node"
                             for n in graph["nodes"]))
        self.assertTrue(any(x["kind"] == "insufficient_direct_support"
                            for x in graph["negative_unknown"]))

    def test_swapped_source_hashes_fail_closed(self):
        node, link = self._synthetic_reports()
        link['source_sha256']['original_r1'] = '2' * 64
        with self.assertRaises(g.GraphBuildError):
            graph_from(node, link)

    def test_one_mate_q14_or_missing_support_withholds_edge(self):
        node, link = self._synthetic_reports()
        for i in range(3):
            link['direct_allele_link_evidence'][i]['supported_direct_local_allele_combinations'] = []
            link['direct_allele_link_evidence'][i]['direct_local_link_supported'] = False
            for k in ('alternative_alternative', 'alternative_reference', 'reference_alternative'):
                link['direct_allele_link_evidence'][i]['observed_joint_original_pair_ids'][k] = 0
                link['direct_allele_link_evidence'][i]['observed_joint_distinct_consistent_pair_sequences'][k] = 0
        graph = graph_from(node, link)
        self.assertFalse(any(e['direct_local_link_supported'] for e in graph['edges']))

    def test_hidden_minor_variant_without_direct_supported_combo_stays_unknown(self):
        node, link = self._synthetic_reports()
        edge = link['direct_allele_link_evidence'][0]
        edge['observed_joint_original_pair_ids'] = {'reference_reference': 0, 'alternative_reference': 0, 'reference_alternative': 0, 'alternative_alternative': 0}
        edge['observed_joint_distinct_consistent_pair_sequences'] = dict(edge['observed_joint_original_pair_ids'])
        edge['supported_direct_local_allele_combinations'] = []
        edge['direct_local_link_supported'] = False
        graph = graph_from(node, link)
        first_pair_edges = [e for e in graph['edges'] if 'pos10::' in e['from'] + e['to'] and 'pos20::' in e['from'] + e['to']]
        self.assertEqual(first_pair_edges, [])
        unknown_pair = [e for e in graph['negative_unknown']
                        if e.get('kind') == 'insufficient_direct_support'
                        and 'pos10::' in e.get('from','') + e.get('to','')
                        and 'pos20::' in e.get('from','') + e.get('to','')]
        self.assertTrue(unknown_pair)
        self.assertTrue(any(u['kind'] == 'insufficient_direct_support' for u in graph['negative_unknown']))

    def test_conflicting_paired_read_calls_not_reported_as_supported(self):
        node, link = self._synthetic_reports()
        edge = link['direct_allele_link_evidence'][0]
        edge['observed_joint_original_pair_ids']['alternative_alternative'] = 4
        edge['observed_joint_distinct_consistent_pair_sequences']['alternative_alternative'] = 4
        edge['supported_direct_local_allele_combinations'] = []
        edge['direct_local_link_supported'] = False
        graph = graph_from(node, link)
        aa = [e for e in graph['negative_unknown']
              if e.get('allele_combination') == 'alternative_alternative'
              and 'pos10::' in e.get('from','') + e.get('to','')
              and 'pos20::' in e.get('from','') + e.get('to','')][0]
        self.assertFalse(aa['direct_local_link_supported'])
        self.assertEqual(aa['kind'], 'insufficient_direct_support')

    def test_no_pcr_duplicate_independent_molecule_claim_and_no_full_length_fabrication(self):
        node, link = self._synthetic_reports()
        graph = graph_from(node, link)
        dumped = json.dumps(graph)
        compact = dumped.lower().replace(' ', '')
        self.assertIn('"independent_physical_molecules_claimed":false', compact)
        self.assertIn('"full_length_haplotype_phase_claimed":false', compact)
        self.assertNotIn('full_length_phased_sequence', dumped.lower())

    def test_cli_checks_sha256_and_writes_private_json(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            reports = root / 'reports'
            reports.mkdir()
            n = reports / 'node.json'
            l = reports / 'link.json'
            # Use a synthetic fixture here so public CI needs no private FASTQ evidence.
            synthetic_node, synthetic_link = self._synthetic_reports()
            n.write_text(json.dumps(synthetic_node, sort_keys=True))
            l.write_text(json.dumps(synthetic_link, sort_keys=True))
            out = root / 'out' / 'test-s48-snv-graph.json'
            import subprocess, sys
            cmd = [sys.executable, 'benchmarks/export_snv_q15_typed_local_graph.py',
                   '--node-report', str(n), '--direct-link-report', str(l),
                   '--sample', '73090AMIDI-MidHCV_S48', '--output', str(out),
                   '--expected-node-report-sha256', sha(n),
                   '--expected-direct-link-report-sha256', sha(l)]
            p = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
            data = json.loads(out.read_text())
            self.assertEqual(data['schema_version'], g.GRAPH_SCHEMA)
            bad = [sys.executable, 'benchmarks/export_snv_q15_typed_local_graph.py',
                   '--node-report', str(n), '--direct-link-report', str(l),
                   '--sample', '73090AMIDI-MidHCV_S48', '--output', str(root / 'out2.json'),
                   '--expected-node-report-sha256', '0' * 64,
                   '--expected-direct-link-report-sha256', sha(l)]
            p2 = subprocess.run(bad, cwd=repo_root, capture_output=True, text=True)
            self.assertNotEqual(p2.returncode, 0)
            self.assertIn('SHA256', p2.stderr + p2.stdout)


if __name__ == '__main__':
    unittest.main()
