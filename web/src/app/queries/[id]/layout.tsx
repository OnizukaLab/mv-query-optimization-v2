import QueryTabs from "@/components/QueryTabs";

export default async function QueryLayout(props: LayoutProps<"/queries/[id]">) {
  const { id } = await props.params;
  return (
    <div className="flex h-full flex-col">
      <QueryTabs queryId={id} />
      <div className="min-h-0 flex-1">{props.children}</div>
    </div>
  );
}
