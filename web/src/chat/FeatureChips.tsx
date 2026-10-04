interface Props {
  selected?: string
  onSelect: (featureId: string | undefined) => void
}

export function FeatureChips({ selected }: Props) {
  // TODO: GET /api/features; choosing one sends feature_id and skips routing.
  return <div role="group" aria-label="Features" data-selected={selected} />
}
