#!/usr/bin/env python3
"""
One-time script to upload PDFs to OpenAI and create permanent vector store.

Usage:
    export OPENAI_API_KEY='your-key-here'
    python scripts/upload-pdfs-to-openai.py

This script:
1. Finds all PDF files in the ./files directory
2. Creates a permanent OpenAI vector store
3. Uploads all PDFs to that vector store
4. Prints the vector store ID to add to GitHub Secrets

After running this script, you'll need to:
1. Copy the OPENAI_VECTOR_STORE_ID value
2. Add it as a GitHub Secret
3. Never run this script again (unless PDFs change)
"""

from openai import OpenAI
import os
import sys
from pathlib import Path

def main():
    print("=" * 70)
    print("ARFID PDF Upload to OpenAI Vector Store")
    print("=" * 70)

    # Check for API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("\n❌ ERROR: OPENAI_API_KEY environment variable not set")
        print("\nPlease set it with:")
        print("  export OPENAI_API_KEY='your-key-here'")
        sys.exit(1)

    # Initialize client
    print("\n✅ OpenAI API key found")
    client = OpenAI(api_key=api_key)

    # Find PDFs
    files_dir = Path(__file__).parent.parent / "files"
    if not files_dir.exists():
        print(f"\n❌ ERROR: Files directory not found: {files_dir}")
        sys.exit(1)

    pdf_files = sorted(list(files_dir.glob("*.pdf")))

    if not pdf_files:
        print(f"\n❌ ERROR: No PDF files found in {files_dir}")
        print("\nMake sure your PDFs are in the ./files directory")
        sys.exit(1)

    print(f"\n✅ Found {len(pdf_files)} PDF files:")
    total_size = 0
    for pdf in pdf_files:
        size_mb = pdf.stat().st_size / (1024 * 1024)
        total_size += size_mb
        print(f"   - {pdf.name} ({size_mb:.2f} MB)")

    print(f"\n📊 Total size: {total_size:.2f} MB")

    # Confirm upload
    print("\n" + "=" * 70)
    response = input("Upload these files to OpenAI? (yes/no): ")
    if response.lower() not in ['yes', 'y']:
        print("Upload cancelled.")
        sys.exit(0)

    # Create vector store
    print("\n📦 Creating permanent vector store...")
    try:
        vector_store = client.vector_stores.create(
            name="ARFID Medical Documents - Production"
        )
        print(f"✅ Vector store created: {vector_store.id}")
    except Exception as e:
        print(f"\n❌ ERROR creating vector store: {e}")
        sys.exit(1)

    # Upload files
    print(f"\n📤 Uploading {len(pdf_files)} PDFs to OpenAI...")
    print("   (This may take several minutes for large files)")

    file_streams = []

    try:
        # Open all file streams
        for pdf_path in pdf_files:
            file_streams.append(open(pdf_path, "rb"))

        # Batch upload with progress polling
        file_batch = client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store.id,
            files=file_streams,
            poll_interval_ms=2000
        )

        # Check status
        if file_batch.status == "completed":
            print(f"\n✅ Upload successful!")
            print(f"   - Completed: {file_batch.file_counts.completed} files")

            if file_batch.file_counts.failed > 0:
                print(f"   - Failed: {file_batch.file_counts.failed} files")

            if file_batch.file_counts.in_progress > 0:
                print(f"   - In progress: {file_batch.file_counts.in_progress} files")

        elif file_batch.status == "in_progress":
            print(f"\n⏳ Upload still in progress...")
            print(f"   - Completed: {file_batch.file_counts.completed} files")
            print(f"   - In progress: {file_batch.file_counts.in_progress} files")
            print("\n   The upload will continue in the background.")
            print("   You can check status at: https://platform.openai.com/storage")

        else:
            print(f"\n❌ Upload failed with status: {file_batch.status}")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ ERROR during upload: {e}")
        sys.exit(1)

    finally:
        # Always close file streams
        for stream in file_streams:
            try:
                stream.close()
            except:
                pass

    # Success! Print instructions
    print("\n" + "=" * 70)
    print("🎉 SUCCESS! PDFs uploaded to OpenAI")
    print("=" * 70)
    print("\n📋 NEXT STEPS:")
    print("\n1. Add this to your GitHub Secrets:")
    print("   " + "-" * 66)
    print(f"   Secret Name:  OPENAI_VECTOR_STORE_ID")
    print(f"   Secret Value: {vector_store.id}")
    print("   " + "-" * 66)

    print("\n2. How to add the secret:")
    print("   a. Go to: https://github.com/YOUR_USERNAME/YOUR_REPO/settings/secrets/actions")
    print("   b. Click 'New repository secret'")
    print("   c. Name: OPENAI_VECTOR_STORE_ID")
    print(f"   d. Value: {vector_store.id}")
    print("   e. Click 'Add secret'")

    print("\n3. For local development, add to your .env file:")
    print(f"   OPENAI_VECTOR_STORE_ID={vector_store.id}")

    print("\n4. Push your code changes:")
    print("   git add .")
    print("   git commit -m 'Migrate to pre-uploaded OpenAI vector store'")
    print("   git push origin main")

    print("\n" + "=" * 70)
    print("💰 Cost Information:")
    print("=" * 70)
    print(f"   Storage: {total_size:.2f} MB")
    print(f"   Rate: $0.10/GB/day")
    print(f"   Estimated monthly cost: ${(total_size / 1024) * 0.10 * 30:.2f}")
    print("\n   Check your usage at: https://platform.openai.com/usage")

    print("\n" + "=" * 70)
    print("✅ Setup Complete!")
    print("=" * 70)

if __name__ == "__main__":
    main()
