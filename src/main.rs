mod assembler;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    assembler::run()
}
