"use client";

import { useEffect, useRef } from "react";
import { DiffEditor, type DiffOnMount } from "@monaco-editor/react";
import { useDarkMode } from "@/lib/useDarkMode";

/** Read-only side-by-side SQL diff. */
export default function SqlDiff({ original, modified }: { original: string; modified: string }) {
  const dark = useDarkMode();
  const editorRef = useRef<Parameters<DiffOnMount>[0] | null>(null);

  // The wrapper disposes the text models before the diff widget; the widget then fires on a
  // disposed model and throws "TextModel got disposed before DiffEditorWidget model got reset".
  // Detaching the models first (this cleanup runs before the child's) avoids the race.
  useEffect(
    () => () => {
      editorRef.current?.setModel(null);
      editorRef.current = null;
    },
    [],
  );

  return (
    <DiffEditor
      original={original}
      modified={modified}
      language="sql"
      theme={dark ? "vs-dark" : "light"}
      onMount={(editor) => {
        editorRef.current = editor;
      }}
      options={{
        readOnly: true,
        renderSideBySide: true,
        minimap: { enabled: false },
        fontSize: 12,
        wordWrap: "on",
        scrollBeyondLastLine: false,
      }}
    />
  );
}
