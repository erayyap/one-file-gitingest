**Using `digest.py`**

1.  **Placement:** Copy `digest.py` into the root directory of your target repository.
2.  **Execution:** Run the script using Python. No external libraries are required.
    *   **Recommended:** For easier review, output to a text file (e.g., `digest.txt`) using the `-o` flag:
        ```bash
        python digest.py . -o digest.txt
        ```
3.  **.gitignore:** To avoid committing the script or its output, add these lines to your `.gitignore` file:
    ```
    digest.py
    digest.txt
    ```
