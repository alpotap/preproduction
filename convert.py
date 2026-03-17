import os
import sys
import win32com.client as win32

def mhtml_to_docx(input_path, output_path=None, visible=False):
    input_path = os.path.abspath(input_path)
    if output_path is None:
        base, _ = os.path.splitext(input_path)
        output_path = base + ".docx"
    output_path = os.path.abspath(output_path)

    # Word constants
    wdFormatXMLDocument = 12  # .docx

    word = win32.gencache.EnsureDispatch("Word.Application")
    word.Visible = visible
    try:
        doc = word.Documents.Open(input_path)
        doc.SaveAs(output_path, FileFormat=wdFormatXMLDocument)
        doc.Close(False)
        print(f"Saved: {output_path}")
    finally:
        word.Quit()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert.py input.mhtml [output.docx]")
        sys.exit(1)
    mhtml_to_docx(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)