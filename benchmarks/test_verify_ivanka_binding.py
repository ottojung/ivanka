import unittest

from verify_ivanka_binding import verify_source


def source(command='["/usr/local/bin/ivanka", "--reads1", str(fastq1), "--reads2", str(fastq2), "--output", str(output)]',
           cache='denovo[ivanka]'):
    return (f'@cached("{cache}")\n'
            'def run_subprocess(fastq1, fastq2, output):\n'
            f'    command = {command}\n'
            '    subprocess.run(command, env={})\n')


class BindingTests(unittest.TestCase):
    def test_valid_ivanka_invocation(self):
        verify_source(source())

    def test_forbid_wrong_binary_even_with_ivanka_text_elsewhere(self):
        fake = ('# command = ["ivanka", "--reads1"]\n' +
                source('["iva", "--reads1", str(fastq1), "--reads2", str(fastq2), "--output", str(output)]'))
        with self.assertRaisesRegex(ValueError, "does not invoke Ivanka"):
            verify_source(fake)

    def test_child_environment_cannot_inherit_or_override_settings(self):
        for value in ("None", '{"IVANKA_BENCH_PRIMARY_SEEDS": "50"}'):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "empty"):
                    verify_source(source().replace("env={}", "env=" + value))

    def test_forbid_mutating_arguments_after_review(self):
        modified = source().replace(
            "    subprocess.run(command, env={})",
            '    command.extend(["--seeds", "other.fasta"])\n'
            "    subprocess.run(command, env={})",
        )
        with self.assertRaisesRegex(ValueError, "mutated"):
            verify_source(modified)

    def test_forbid_extra_nonessential_flag(self):
        command = ('["/usr/local/bin/ivanka", "--reads1", str(fastq1), '
                   '"--reads2", str(fastq2), "--output", str(output), '
                   '"--max-contigs", "16"]')
        with self.assertRaisesRegex(ValueError, "both mates|three CLI"):
            verify_source(source(command=command))

    def test_forbid_wrong_cache_key(self):
        with self.assertRaisesRegex(ValueError, "cache key"):
            verify_source(source(cache="denovo[iva]"))

    def test_forbid_duplicate_assembler_definition(self):
        with self.assertRaisesRegex(ValueError, "Exactly one"):
            verify_source(source() + '\ndef run_subprocess():\n    return None\n')

    def test_forbid_missing_mate_argument(self):
        with self.assertRaisesRegex(ValueError, "both mates"):
            verify_source(source('["/usr/local/bin/ivanka", "--reads1", str(fastq1), "--output", str(output)]'))


if __name__ == "__main__":
    unittest.main()
