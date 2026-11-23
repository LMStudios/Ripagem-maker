const path=require('node:path');
module.exports=context=>require('./verify-engine.cjs').verify(context,path.resolve(__dirname,'../engine-windows'));
