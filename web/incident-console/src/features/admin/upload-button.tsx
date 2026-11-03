import { UploadIcon } from "lucide-react";
import { useRef } from "react";
import { Button } from "@/components/ui/button";

/** A button that opens the file picker; the files go to `onFiles` and the input is cleared. */
export function UploadButton({
  id,
  label,
  accept,
  multiple = false,
  onFiles,
}: {
  id: string;
  label: string;
  accept: string;
  multiple?: boolean;
  onFiles: (files: File[]) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <input
        ref={input}
        id={id}
        type="file"
        className="sr-only"
        tabIndex={-1}
        accept={accept}
        multiple={multiple}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          event.target.value = "";
          if (files.length) onFiles(files);
        }}
      />
      <Button type="button" variant="outline" onClick={() => input.current?.click()}>
        <UploadIcon /> {label}
      </Button>
    </>
  );
}
