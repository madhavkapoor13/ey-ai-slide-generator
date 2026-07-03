#!/usr/bin/env python3
import os
import sys
import httpx
import urllib3

# Suppress insecure request warnings for self-signed developer certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BACKEND_URL = "https://127.0.0.1:8000"
PROMPTS = {
    "nike_finance": "Build me a current state slide for Nike Finance.",
    "toyota_procurement": "Build me a current state slide for Toyota Procurement.",
    "microsoft_hr": "Build me a current state slide for Microsoft HR."
}

def main():
    # Make sure we run from the project root if executing as scripts/run_comparison.py
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(project_root, "test_outputs")
    os.makedirs(output_dir, exist_ok=True)

    print("==================================================")
    # Highlight style formatting for headers
    print("      EY AI Slide Generator: Comparison Runner     ")
    print("==================================================")
    print(f"Target Backend: {BACKEND_URL}")
    print(f"Saving outputs to: {output_dir}\n")

    # Verify backend is running first
    with httpx.Client(verify=False) as client:
        try:
            r = client.get(BACKEND_URL)
            print(f"Backend Status Check: {r.status_code} OK - {r.json()}\n")
        except Exception as e:
            print(f"ERROR: Cannot connect to backend at {BACKEND_URL}.")
            print("Please make sure the backend is running by executing:")
            print("  ./scripts/start_backend_https.sh")
            sys.exit(1)

        for key, prompt in PROMPTS.items():
            print(f"\n--- Testing Scenario: {key.replace('_', ' ').title()} ---")
            print(f"Prompt: \"{prompt}\"")

            for phase, endpoint in [("Phase 1", "generate"), ("Phase 2", "generate/v2")]:
                url = f"{BACKEND_URL}/{endpoint}"
                filename = f"{key}_{endpoint.replace('/', '_')}.pptx"
                filepath = os.path.join(output_dir, filename)

                print(f" -> Sending request to {phase} ({url})...", end="", flush=True)

                try:
                    # Timeout set to 90 seconds to allow for deep orchestration and validation
                    resp = client.post(
                        url,
                        json={"title": "Current State", "content": prompt},
                        timeout=90.0
                    )

                    if resp.status_code == 200:
                        with open(filepath, "wb") as f:
                            f.write(resp.content)
                        size_kb = len(resp.content) / 1024
                        print(f" [SUCCESS] Saved to {filename} ({size_kb:.1f} KB)")
                    elif resp.status_code == 422:
                        print(f" [VALIDATION FAILED] Code {resp.status_code}")
                        print(f"    Detail: {resp.text}")
                    else:
                        print(f" [FAILED] Code {resp.status_code}")
                        print(f"    Detail: {resp.text}")

                except Exception as e:
                    print(f" [ERROR] Connection/Timeout issue: {e}")

    print("\n==================================================")
    print("Tests completed! Open the slides in 'test_outputs/' to compare:")
    print("1. Executive Summary")
    print("2. Process Selection")
    print("3. Activities")
    print("4. Pain Points")
    print("5. Overall Consulting Quality")
    print("==================================================")

if __name__ == "__main__":
    main()
