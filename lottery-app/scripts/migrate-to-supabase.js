const fs = require('fs')
const path = require('path')
async function main(){
  const SUPABASE_URL = process.env.SUPABASE_URL
  const SUPABASE_KEY = process.env.SUPABASE_KEY
  if(!SUPABASE_URL || !SUPABASE_KEY){
    console.error('Missing SUPABASE_URL or SUPABASE_KEY in env')
    process.exit(2)
  }
  const { createClient } = require('@supabase/supabase-js')
  const supabase = createClient(SUPABASE_URL, SUPABASE_KEY)
  const types = ['lotto','pension']
  for(const t of types){
    const p = path.join(__dirname,'..','data', `${t}.json`)
    if(!fs.existsSync(p)){
      console.error(`${t}: data file not found: ${p}`)
      continue
    }
    try{
      const rows = JSON.parse(fs.readFileSync(p,'utf8'))
      console.log(`${t}: read ${Array.isArray(rows)?rows.length:0} rows`)
      // Postgres folds unquoted identifiers to lowercase. Ensure column names match
      // by converting JSON keys to lowercase before upsert.
      const normalized = rows.map(r => {
        const out = {}
        for(const k of Object.keys(r)){
          out[k.toLowerCase()] = r[k]
        }
        return out
      })
      const conflictKey = t === 'lotto' ? 'drwno' : 'round'
      const { data, error } = await supabase.from(t).upsert(normalized, { onConflict: [conflictKey] })
      if(error){
        console.error(`${t}: upsert error:`, error.message || JSON.stringify(error))
      } else {
        console.log(`${t}: upsert OK`)
      }
    }catch(e){
      console.error(`${t}: error`, e.message)
    }
  }
}

main().then(()=>process.exit(0)).catch(e=>{console.error('fatal',e);process.exit(1)})
