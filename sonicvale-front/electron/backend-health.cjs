function isAuralisHealth(status,body) {
  if(status!==200)return false
  try {const value=JSON.parse(body);return value.application==='auralis'&&value.api_version===1&&value.ready===true}
  catch{return false}
}
module.exports={isAuralisHealth}
