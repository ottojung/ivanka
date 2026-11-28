"""Assembler branch tests: fixed command, paired input and failure behavior."""
from pathlib import Path
import subprocess
import pytest

from micall.core import denovo
from micall.core.benchmark_assembler import assemble
from micall.utils.work_dir import WorkDir


TOOL = "unicycler"


def sample_reads(tmp_path):
    first, second = tmp_path / "R1.fastq", tmp_path / "R2.fastq"
    for path, mate in ((first, 1), (second, 2)):
        path.write_text(f"@sample/{mate}\n" + "ACGT" * 40
                        + "\n+\n" + "I" * 160 + "\n")
    return first, second


def expected_output(work):
    return work / "unicycler" / "assembly.fasta"


def write_output(work, content=">contig\nACGT\n"):
    output = expected_output(work)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content)
    return output


def test_only_fixed_assembler_is_invoked(tmp_path, monkeypatch):
    first, second = sample_reads(tmp_path)
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(([str(a) for a in argv], kwargs))
        write_output(Path(kwargs["cwd"]))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr("micall.core.benchmark_assembler.subprocess.run", fake_run)
    with WorkDir.using(tmp_path):
        output = assemble(first, second, None)
    assert output.read_text() == ">contig\nACGT\n"
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv[0] == TOOL
    assert kwargs["check"] is True
    assert kwargs["stdout"] is not None
    assert kwargs["stderr"] == subprocess.STDOUT
    assert kwargs["env"] is None
    assert Path(kwargs["cwd"]).is_dir()


def test_paired_fastq_is_reference_blind(tmp_path, monkeypatch):
    first, second = sample_reads(tmp_path)
    seeds = tmp_path / "consensus.csv"
    seeds.write_text("contig\nACGTACGTACGT\n")
    seen = []

    def fake_run(argv, **kwargs):
        seen.append([str(a) for a in argv])
        write_output(Path(kwargs["cwd"]))

    monkeypatch.setattr("micall.core.benchmark_assembler.subprocess.run", fake_run)
    with WorkDir.using(tmp_path):
        assemble(first, second, seeds)
    argv = seen[0]
    assert argv[argv.index("-1") + 1] == str(first)
    assert argv[argv.index("-2") + 1] == str(second)
    joined = " ".join(argv).lower()
    for banned in ("--reference", "--ref", "-r ", "ref=", "seeds",
                   "--contigs", "--targets", "hxb2", "sra_run", "--genome"):
        assert banned not in joined
    assert "consensus.csv" not in joined


def test_zero_contig_empty_fasta_is_valid(tmp_path, monkeypatch):
    first, second = sample_reads(tmp_path)

    def fake_run(argv, **kwargs):
        write_output(Path(kwargs["cwd"]), "")

    monkeypatch.setattr("micall.core.benchmark_assembler.subprocess.run", fake_run)
    with WorkDir.using(tmp_path):
        output = assemble(first, second, None)
    assert output.is_file()
    assert output.read_text() == ""
    assert denovo.count_fasta_sequences(output) == 0


def test_missing_fasta_is_rejected(tmp_path, monkeypatch):
    first, second = sample_reads(tmp_path)

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr("micall.core.benchmark_assembler.subprocess.run", fake_run)
    with WorkDir.using(tmp_path), pytest.raises(
        RuntimeError, match="without the expected FASTA"
    ):
        assemble(first, second, None)


def test_denovo_bridge_uses_fixed_assembler_without_runtime_selector(tmp_path,
                                                                     monkeypatch):
    first, second = sample_reads(tmp_path)
    calls = []

    def fake_assemble(fastq1, fastq2, seeds):
        calls.append((fastq1, fastq2, seeds))
        output = tmp_path / "bridged.fasta"
        output.write_text(">contig\nACGT\n")
        return output

    monkeypatch.setattr("micall.core.benchmark_assembler.assemble", fake_assemble)
    monkeypatch.setenv("MICALL_DENOVO_ASSEMBLER", "spades")
    with WorkDir.using(tmp_path):
        result = denovo.run_subprocess.__wrapped__(first, second, None)
    assert result == tmp_path / "bridged.fasta"
    assert calls == [(first, second, None)]
