import Workspace from "@/components/Workspace";

export default async function QueryPage(props: PageProps<"/queries/[id]">) {
  const { id } = await props.params;
  const { node } = await props.searchParams;
  return <Workspace key={`${id}:${node ?? ""}`} queryId={id} focusNodeId={typeof node === "string" ? node : undefined} />;
}
