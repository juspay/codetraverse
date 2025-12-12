#!/bin/bash
set -u # removed -e so we can handle errors manually

echo "Building Rust fdep-ra client..."
cd src/rust_fdep/fdep-ra

if cargo build --release; then
    echo "Rust fdep-ra client built successfully at src/rust_fdep/fdep-ra/target/release/fdep-ra"
else
    echo "Failed to build Rust fdep-ra client."
    exit 1
fi