import Workspace from "@/components/Workspace";

export default async function QueryPage(props: PageProps<"/queries/[id]">) {
  const { id } = await props.params;
  const { node, mode, mv } = await props.searchParams;
  return (
    <Workspace
      key={`${id}:${node ?? ""}:${typeof mv === "string" ? mv : ""}`}
      queryId={id}
      focusNodeId={typeof node === "string" ? node : undefined}
      initialMode={mode === "mv" ? "mv" : "plan"}
      initialMvNodes={typeof mv === "string" ? [mv] : []}
    />
  );
}
