# Pigment Library

## V1 Status

PARTIAL. Fenran V1 records apparent display palette from the original image, but it does not claim real pigment ratios.

## Intended Schema

- Pigment: id, brand, name, pigment_type, metadata.
- Paper: id, brand, name, paper_type, metadata.
- PigmentSample: sample id, paper id, pigment ratios, water ratio, glue ratio, layer count, dry Lab, optional image URI.

## Current Safe Behavior

When measured pigment samples are unavailable, the system must return no reliable pigment recipe rather than inventing ratios.
