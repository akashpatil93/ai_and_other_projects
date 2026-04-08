interface Props {
  status: string
}

const STEPS = [
  'Uploading document',
  'Parsing sheets & sections',
  'Classifying policy sections',
  'Extracting rules with Claude AI',
  'Assembling workflow JSON',
  'Validating output',
]

export default function ProcessingStatus({ status }: Props) {
  return (
    <div className="max-w-xl mx-auto text-center py-16">
      {/* Spinner */}
      <div className="inline-flex items-center justify-center w-20 h-20 bg-indigo-50 rounded-full mb-6">
        <div className="w-10 h-10 border-4 border-indigo-600 border-t-transparent rounded-full animate-spin" />
      </div>

      <h2 className="text-2xl font-bold text-gray-900 mb-2">Generating Workflow</h2>
      <p className="text-indigo-600 font-medium text-lg mb-1">{status}</p>
      <p className="text-gray-400 text-sm">This may take up to 60 seconds for large documents</p>

      {/* Step list */}
      <div className="mt-8 space-y-2.5 text-left max-w-xs mx-auto">
        {STEPS.map((step, i) => (
          <div key={i} className="flex items-center gap-3 text-sm text-gray-500">
            <div className="w-4 h-4 rounded-full bg-indigo-100 flex items-center justify-center shrink-0">
              <div className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
            </div>
            {step}
          </div>
        ))}
      </div>
    </div>
  )
}
