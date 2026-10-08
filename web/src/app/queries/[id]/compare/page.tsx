import QueryCompare from "@/components/QueryCompare";

export default async function QueryComparePage(props: PageProps<"/queries/[id]/compare">) {
  const { id } = await props.params;
  return <QueryCompare key={id} queryId={id} />;
}
