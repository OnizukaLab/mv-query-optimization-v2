import Workspace from "@/components/Workspace";

export default async function QueryPage(props: PageProps<"/queries/[id]">) {
  const { id } = await props.params;
  return <Workspace key={id} queryId={id} />;
}
