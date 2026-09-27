/**
 * Downloadable CSV templates for the upload wizard.
 *
 * The sample rows are obviously fictional and internally consistent: they
 * satisfy every rule the validator applies, so a merchant who fills the
 * template in the same shape will pass first time. Handing someone a template
 * that fails our own validation would be worse than handing them nothing.
 */
const SALES_TEMPLATE = `date,product,category,orders,units_sold,revenue,expenses,inventory
2026-03-01,Masala Chai,Beverages,42,42,2100,840,158
2026-03-01,Veg Sandwich,Food,18,18,1620,810,82
2026-03-02,Masala Chai,Beverages,38,38,1900,760,120
2026-03-02,Veg Sandwich,Food,21,21,1890,945,61
2026-03-03,Masala Chai,Beverages,45,45,2250,900,75
2026-03-03,Veg Sandwich,Food,17,17,1530,765,44
`

const CUSTOMERS_TEMPLATE = `date,customers,new_customers,repeat_customers
2026-03-01,52,31,21
2026-03-02,48,22,26
2026-03-03,55,25,30
`

export const templates = {
  sales: {
    filename: 'merchantai-sales-template.csv',
    content: SALES_TEMPLATE,
  },
  customers: {
    filename: 'merchantai-customers-template.csv',
    content: CUSTOMERS_TEMPLATE,
  },
}

/** Trigger a browser download of one template. */
export function downloadTemplate(uploadType) {
  const template = templates[uploadType]
  if (!template) return

  const url = URL.createObjectURL(new Blob([template.content], { type: 'text/csv' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = template.filename
  anchor.click()
  URL.revokeObjectURL(url)
}
