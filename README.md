# Image Factory

Automated container image building and promotion system using Kargo and ArgoCD.

## Overview

The Image Factory automates the process of building, analyzing, and promoting container images through a GitOps workflow. It uses Kargo for orchestration and generates Kubernetes resources via CDK8s.

## Repository Structure

```
.
├── app/                 # Python analysis tool for Dockerfile validation
├── cdk8s/              # CDK8s application for generating Kargo resources
│   ├── lib/            # Reusable CDK8s constructs
│   ├── imports/        # Generated Kargo CRD imports
│   └── main.py         # Main CDK8s application
├── tests/              # Integration and acceptance tests
│   └── integration/    # Integration test suite
└── Taskfile.yaml       # Task automation
```

**Note**: Configuration files (`images.yaml`, state files) and generated manifests (`dist/`) are maintained in the separate [image-factory-state](https://github.com/craigedmunds/image-factory-state) repository.

**Archived Documentation**: Historical design docs, requirements, and workflow documentation are archived in `workspace-root/.ai/projects/infrastructure/image-factory/`.

## Related Repositories

- **[image-factory-state](https://github.com/craigedmunds/image-factory-state)** - State files for base images, application images, and generated Kargo manifests
- **[argocd-eda](https://github.com/craigedmunds/argocd-eda)** - Platform repository that deploys Image Factory

## Configuration

### State Repository

The Image Factory separates code from configuration by using an external state repository. By default, it looks for the state repository at `../image-factory-state` relative to the `cdk8s/` directory.

**Override the state directory location:**

```bash
export IMAGE_FACTORY_STATE_DIR=/path/to/image-factory-state
```

**State repository structure:**

```
image-factory-state/
├── images.yaml              # Image enrollment registry
├── base-images/            # Base image configurations
│   ├── node-22-bookworm-slim.yaml
│   └── python-3.12-slim.yaml
├── images/                 # Application image configurations
│   ├── backstage.yaml
│   └── uv.yaml
└── dist/                   # Generated Kargo manifests (CDK8s output)
    └── image-factory.k8s.yaml
```

See [image-factory-state](https://github.com/craigedmunds/image-factory-state) for the production configuration.

## Development

### Setup

```bash
# Set up all components
task test:unit:setup

# Or set up individually
task app:setup
task cdk8s:setup
```

### Generating Kargo Resources

The CDK8s application reads configuration from the state repository and generates Kargo manifests:

```bash
cd cdk8s
.venv/bin/python main.py
```

The generated resources will be in `../image-factory-state/dist/image-factory.k8s.yaml`.

### Testing

```bash
# Run all tests
task test:all

# Run specific test suites
task test:unit           # Unit tests for app and cdk8s
task test:integration    # Integration tests
task test:acceptance     # Kargo acceptance tests
```

### Debugging

```bash
# View logs from recent analysis runs
task logs:analysis

# Quick view of latest analysis logs
task logs:analysis:latest
```

## How It Works

1. **Image Enrollment**: Images are defined in `images.yaml` in the state repository
2. **State Files**: Detailed configuration for each image in `base-images/` and `images/` directories
3. **CDK8s Generation**: The CDK8s app reads state files and generates Kargo Warehouses, Stages, and AnalysisTemplates
4. **ArgoCD Deployment**: ArgoCD watches the state repository's `dist/` directory and deploys the generated manifests
5. **Kargo Orchestration**: Kargo manages the image build and promotion pipeline

## Image Types

### Base Images
Foundational container images that application images build upon.

Examples:
- **Node.js**: `node-22-bookworm-slim`
- **Python**: `python-3.12-slim`
- **Distroless**: `gcr.io/distroless/python3-debian12`

### Application Images
Built on top of base images and represent deployable applications.

Examples:
- **Backstage**: Developer portal application
- **UV Service**: Python utility service
- **Metrics Service**: Market making metrics collector

## Deployment

The Image Factory is deployed via ArgoCD. See the [argocd-eda](https://github.com/craigedmunds/argocd-eda) repository for deployment configuration.

ArgoCD watches: `https://github.com/craigedmunds/image-factory-state.git` at path `dist/`

## Troubleshooting

### CDK8s Synthesis Issues

If synthesis fails, check:
1. State repository is accessible at `../image-factory-state`
2. All required state files exist (`images.yaml`, `base-images/`, `images/`)
3. YAML files are valid

### State Directory Not Found

Set the `IMAGE_FACTORY_STATE_DIR` environment variable:

```bash
export IMAGE_FACTORY_STATE_DIR=/path/to/image-factory-state
cd cdk8s
.venv/bin/python main.py
```

## Contributing

1. Make changes to the code in this repository
2. Update state files in the [image-factory-state](https://github.com/craigedmunds/image-factory-state) repository
3. Run tests: `task test:all`
4. Generate manifests: `cd cdk8s && .venv/bin/python main.py`
5. Commit and push both repositories

## Related Documentation

- [Kargo Documentation](https://docs.akuity.io/kargo/)
- [CDK8s Documentation](https://cdk8s.io/)
- [Image Factory State Repository](https://github.com/craigedmunds/image-factory-state)
