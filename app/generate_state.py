#!/usr/bin/env python3
"""
Generate state files from images.yaml.

This script reads images.yaml and generates state files in base-images/ and images/
directories by analyzing Dockerfiles to discover base image dependencies.
"""
import yaml
import sys
import re
from pathlib import Path
import subprocess
import argparse


def load_images_yaml(images_yaml_path: Path) -> list:
    """Load and parse images.yaml."""
    with open(images_yaml_path) as f:
        return yaml.safe_load(f) or []


def parse_dockerfile_base_images(dockerfile_path: Path) -> list:
    """Extract all base images from Dockerfile FROM statements (multi-stage support)."""
    if not dockerfile_path.exists():
        print(f"Warning: Dockerfile not found: {dockerfile_path}", file=sys.stderr)
        return []
    
    base_images = []
    with open(dockerfile_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('FROM '):
                # Extract image reference, handle AS alias
                match = re.match(r'FROM\s+([^\s]+)', line)
                if match:
                    image_ref = match.group(1)
                    # Skip scratch and stage references
                    if image_ref.lower() != 'scratch' and not is_stage_reference(image_ref):
                        base_images.append(image_ref)
    
    return base_images


def is_stage_reference(image_ref: str) -> bool:
    """Check if image reference is a stage name (not a real image)."""
    # Stage names are typically lowercase and don't contain registry/repository patterns
    if '/' in image_ref or ':' in image_ref or '.' in image_ref:
        return False
    # Stage names are usually simple identifiers
    return image_ref.islower() and len(image_ref) < 20


def normalize_base_image_name(image_ref: str) -> str:
    """Convert image reference to normalized name for filename."""
    # Replace special chars with hyphens
    name = re.sub(r'[:/]', '-', image_ref)
    return name


def clone_repo_if_needed(source: dict, dockerfile_path: str, cache_dir: Path) -> Path:
    """
    Clone a git repository (sparse checkout of just the Dockerfile) to cache directory.
    Returns the path to the cloned repo.
    """
    provider = source.get("provider", "github")
    repo = source.get("repo")
    branch = source.get("branch", "main")
    
    if not repo:
        raise ValueError("No repo specified in source")
    
    # Build git URL
    if provider == "github":
        git_url = f"https://github.com/{repo}.git"
    elif provider == "gitlab":
        git_url = f"https://gitlab.com/{repo}.git"
    else:
        raise ValueError(f"Unknown provider: {provider}")
    
    # Create cache directory for this repo
    repo_cache_dir = cache_dir / repo.replace("/", "_")
    dockerfile_full_path = repo_cache_dir / dockerfile_path
    
    if dockerfile_full_path.exists():
        print(f"  Using cached Dockerfile: {dockerfile_full_path}")
        return repo_cache_dir
    
    print(f"  Fetching {dockerfile_path} from {git_url} (branch: {branch})...")
    
    # Use sparse checkout to only fetch the Dockerfile
    repo_cache_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        # Initialize git repo
        subprocess.run(
            ["git", "init"],
            cwd=repo_cache_dir,
            check=True,
            capture_output=True
        )
        
        # Enable sparse checkout
        subprocess.run(
            ["git", "config", "core.sparseCheckout", "true"],
            cwd=repo_cache_dir,
            check=True,
            capture_output=True
        )
        
        # Specify which files to checkout
        sparse_checkout_file = repo_cache_dir / ".git" / "info" / "sparse-checkout"
        sparse_checkout_file.parent.mkdir(parents=True, exist_ok=True)
        with open(sparse_checkout_file, 'w') as f:
            f.write(f"{dockerfile_path}\n")
        
        # Add remote
        subprocess.run(
            ["git", "remote", "add", "origin", git_url],
            cwd=repo_cache_dir,
            check=True,
            capture_output=True
        )
        
        # Fetch and checkout
        subprocess.run(
            ["git", "fetch", "--depth", "1", "origin", branch],
            cwd=repo_cache_dir,
            check=True,
            capture_output=True
        )
        
        subprocess.run(
            ["git", "checkout", branch],
            cwd=repo_cache_dir,
            check=True,
            capture_output=True
        )
        
        print(f"  Fetched to {repo_cache_dir}")
        
    except subprocess.CalledProcessError as e:
        print(f"  Error during git operations: {e}", file=sys.stderr)
        # Clean up partial clone
        import shutil
        shutil.rmtree(repo_cache_dir, ignore_errors=True)
        raise
    
    return repo_cache_dir


def generate_state_for_image(image: dict, output_dir: Path, cache_dir: Path) -> bool:
    """
    Generate state file for a single image by analyzing its Dockerfile.
    
    Simulates what Kargo does: clone repo, analyze Dockerfile, discover base images.
    """
    name = image.get("name")
    if not name:
        print(f"Skipping image without name: {image}", file=sys.stderr)
        return False
    
    # Determine if this is a base image or application image
    # Check both input format (top-level source) and state format (enrollment.source)
    source = image.get("source", {})
    if not source:
        enrollment = image.get("enrollment", {})
        source = enrollment.get("source", {})
    
    is_base_image = not source  # Base images don't have source
    
    # Create state directory
    if is_base_image:
        state_dir = output_dir / "base-images"
    else:
        state_dir = output_dir / "images"
    
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / f"{name}.yaml"
    
    # For base images, just copy the config
    if is_base_image:
        with open(state_file, 'w') as f:
            yaml.dump(image, f, default_flow_style=False)
        print(f"✓ Generated state for base image: {name}")
        return True
    
    # For application images, analyze Dockerfile to discover base images
    dockerfile_path = source.get("dockerfile")
    base_images = []
    
    if dockerfile_path:
        # Clone the repo if needed (sparse checkout of just the Dockerfile)
        try:
            repo_dir = clone_repo_if_needed(source, dockerfile_path, cache_dir)
            full_dockerfile_path = repo_dir / dockerfile_path
            
            if full_dockerfile_path.exists():
                discovered = parse_dockerfile_base_images(full_dockerfile_path)
                # Normalize and deduplicate base image names
                seen = set()
                for base_image_ref in discovered:
                    base_image_name = normalize_base_image_name(base_image_ref)
                    if base_image_name not in seen:
                        base_images.append(base_image_name)
                        seen.add(base_image_name)
                
                if base_images:
                    print(f"  Discovered {len(base_images)} base images: {base_images}")
            else:
                print(f"  Warning: Dockerfile not found at {full_dockerfile_path}", file=sys.stderr)
        except Exception as e:
            print(f"  Error fetching/analyzing Dockerfile: {e}", file=sys.stderr)
    
    # Wrap input in enrollment structure for state file
    # Input format: top-level registry, repository, source
    # State format: enrollment wrapper + metadata fields
    enrollment_data = {}
    for key in ['registry', 'repository', 'source', 'rebuildDelay', 'autoRebuild', 'updates']:
        if key in image:
            enrollment_data[key] = image[key]
    
    state_data = {
        "name": name,
        "enrollment": enrollment_data,
        "baseImages": sorted(base_images),  # Add discovered base images
        "lastAnalyzed": None,
        "analysisStatus": "pending",
    }
    
    with open(state_file, 'w') as f:
        yaml.dump(state_data, f, default_flow_style=False)
    
    print(f"✓ Generated state for application image: {name}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Generate state files from images.yaml")
    parser.add_argument(
        "--images-yaml",
        type=Path,
        required=True,
        help="Path to images.yaml"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for state files (will create base-images/ and images/ subdirs)"
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="Cache directory for cloned repos (default: .image-factory-cache in output dir)"
    )
    
    args = parser.parse_args()
    
    if not args.images_yaml.exists():
        print(f"Error: images.yaml not found at {args.images_yaml}", file=sys.stderr)
        sys.exit(1)
    
    # Set up cache directory
    if args.cache_dir:
        cache_dir = args.cache_dir
    else:
        cache_dir = args.output_dir / ".image-factory-cache"
    
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Load images
    images = load_images_yaml(args.images_yaml)
    print(f"Found {len(images)} images in {args.images_yaml}")
    
    # Generate state for each image
    success_count = 0
    for image in images:
        if generate_state_for_image(image, args.output_dir, cache_dir):
            success_count += 1
    
    print(f"\n✓ Generated state files for {success_count}/{len(images)} images")
    print(f"  Base images: {args.output_dir}/base-images/")
    print(f"  Application images: {args.output_dir}/images/")


if __name__ == "__main__":
    main()
