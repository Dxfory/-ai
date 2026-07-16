# Fenran Limitations

- Subject masks are deterministic image masks, not object-level semantic segmentation.
- Boundary and stage metrics cannot prove every petal, leaf, branch, or insect is semantically present; uncertain outputs remain `review_required`.
- Local registration still depends on the existing manual approval workflow and does not automatically solve topology changes.
- Apparent colors are measured from the original image; they are not laboratory pigment recipes.
- The provider must accept the OpenAI-compatible multi-image edit request shape.
