import os
import mapscript

def create_symbol_file(symbol_file):
    created = False
    if not os.path.exists(symbol_file):
        symbol_obj = mapscript.symbolSetObj()
        symbol = mapscript.symbolObj("horizline")
        symbol.name = "horizline"
        symbol.type = mapscript.MS_SYMBOL_VECTOR
        po = mapscript.pointObj()
        po.setXY(0, 0)
        lo = mapscript.lineObj()
        lo.add(po)
        po.setXY(1, 0)
        lo.add(po)
        symbol.setPoints(lo)
        symbol_obj.appendSymbol(symbol)

        # Create vector arrow
        symbol_wa = mapscript.symbolObj("vector_arrow")
        symbol_wa.name = "vector_arrow"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(10,3))
        lo.add(mapscript.pointObj(6,6))
        lo.add(mapscript.pointObj(7,3.75))
        lo.add(mapscript.pointObj(0,3.75))
        lo.add(mapscript.pointObj(0,2.25))
        lo.add(mapscript.pointObj(7,2.25))
        lo.add(mapscript.pointObj(6,0))
        lo.add(mapscript.pointObj(10,3))
        symbol_wa.setPoints(lo)
        symbol_wa.anchorpoint_x = 1.
        symbol_wa.anchorpoint_y = 0.5
        symbol_wa.filled = True
        symbol_obj.appendSymbol(symbol_wa)

        # # Create wind barb 5 kn
        # symbol_wa = mapscript.symbolObj("wind_barb_5")
        # symbol_wa.name = "wind_barb_5"
        # symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        # lo = mapscript.lineObj()
        # lo.add(mapscript.pointObj(2,8.2))
        # lo.add(mapscript.pointObj(26,8.2))
        # lo.add(mapscript.pointObj(-99,-99))
        # lo.add(mapscript.pointObj(4,8.2))
        # lo.add(mapscript.pointObj(3,3.5))
        # symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        # symbol_wa.filled = False
        # symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 0 kn
        symbol_wa = mapscript.symbolObj("wind_barb_0")
        symbol_wa.name = "wind_barb_0"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 5 kn
        symbol_wa = mapscript.symbolObj("wind_barb_5")
        symbol_wa.name = "wind_barb_5"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(3,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)


        # Create wind barb 10 kn
        symbol_wa = mapscript.symbolObj("wind_barb_10")
        symbol_wa.name = "wind_barb_10"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)


        # Create wind barb 15 kn
        symbol_wa = mapscript.symbolObj("wind_barb_15")
        symbol_wa.name = "wind_barb_15"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(3,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 20 kn
        symbol_wa = mapscript.symbolObj("wind_barb_20")
        symbol_wa.name = "wind_barb_20"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(2.3,0))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 25 kn
        symbol_wa = mapscript.symbolObj("wind_barb_25")
        symbol_wa.name = "wind_barb_25"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(2.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(6,8.2))
        lo.add(mapscript.pointObj(5,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 30 kn
        symbol_wa = mapscript.symbolObj("wind_barb_30")
        symbol_wa.name = "wind_barb_30"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(2.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(6,8.2))
        lo.add(mapscript.pointObj(4.3,0))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 35 kn
        symbol_wa = mapscript.symbolObj("wind_barb_35")
        symbol_wa.name = "wind_barb_35"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(2.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(6,8.2))
        lo.add(mapscript.pointObj(4.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(7,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 40 kn
        symbol_wa = mapscript.symbolObj("wind_barb_40")
        symbol_wa.name = "wind_barb_40"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(2.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(6,8.2))
        lo.add(mapscript.pointObj(4.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(6.3,0))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 45 kn
        symbol_wa = mapscript.symbolObj("wind_barb_45")
        symbol_wa.name = "wind_barb_45"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(0.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(4,8.2))
        lo.add(mapscript.pointObj(2.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(6,8.2))
        lo.add(mapscript.pointObj(4.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(6.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(10,8.2))
        lo.add(mapscript.pointObj(9,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 50 kn
        symbol_wa = mapscript.symbolObj("wind_barb_50")
        symbol_wa.name = "wind_barb_50"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 50 kn
        symbol_wa = mapscript.symbolObj("wind_barb_50_flag")
        symbol_wa.name = "wind_barb_50_flag"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        #lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(4.4,0))
        lo.add(mapscript.pointObj(6.8,8.2))
        lo.add(mapscript.pointObj(2,8.2)) # Join start
        #lo.add(mapscript.pointObj(26,8.2)) # Join start
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = True
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 55 kn
        symbol_wa = mapscript.symbolObj("wind_barb_55")
        symbol_wa.name = "wind_barb_55"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(7,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 60 kn
        symbol_wa = mapscript.symbolObj("wind_barb_60")
        symbol_wa.name = "wind_barb_60"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(6.3,0))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)




        # Create wind barb 65 kn
        symbol_wa = mapscript.symbolObj("wind_barb_65")
        symbol_wa.name = "wind_barb_65"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(6.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(10,8.2))
        lo.add(mapscript.pointObj(9,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 70 kn
        symbol_wa = mapscript.symbolObj("wind_barb_70")
        symbol_wa.name = "wind_barb_70"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(6.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(10,8.2))
        lo.add(mapscript.pointObj(8.3,0))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 75 kn
        symbol_wa = mapscript.symbolObj("wind_barb_75")
        symbol_wa.name = "wind_barb_75"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(6.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(10,8.2))
        lo.add(mapscript.pointObj(8.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(12,8.2))
        lo.add(mapscript.pointObj(11,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 80 kn
        symbol_wa = mapscript.symbolObj("wind_barb_80")
        symbol_wa.name = "wind_barb_80"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(6.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(10,8.2))
        lo.add(mapscript.pointObj(8.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(12,8.2))
        lo.add(mapscript.pointObj(10.3,0))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 85 kn
        symbol_wa = mapscript.symbolObj("wind_barb_85")
        symbol_wa.name = "wind_barb_85"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(6.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(10,8.2))
        lo.add(mapscript.pointObj(8.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(12,8.2))
        lo.add(mapscript.pointObj(10.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(14,8.2))
        lo.add(mapscript.pointObj(13,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 90 kn
        symbol_wa = mapscript.symbolObj("wind_barb_90")
        symbol_wa.name = "wind_barb_90"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(6.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(10,8.2))
        lo.add(mapscript.pointObj(8.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(12,8.2))
        lo.add(mapscript.pointObj(10.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(14,8.2))
        lo.add(mapscript.pointObj(12.3,0))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 95 kn
        symbol_wa = mapscript.symbolObj("wind_barb_95")
        symbol_wa.name = "wind_barb_95"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(8,8.2))
        lo.add(mapscript.pointObj(6.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(10,8.2))
        lo.add(mapscript.pointObj(8.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(12,8.2))
        lo.add(mapscript.pointObj(10.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(14,8.2))
        lo.add(mapscript.pointObj(12.3,0))
        lo.add(mapscript.pointObj(-99,-99))
        lo.add(mapscript.pointObj(16,8.2))
        lo.add(mapscript.pointObj(15,3.5))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)

        # Create wind barb 100 kn
        symbol_wa = mapscript.symbolObj("wind_barb_100")
        symbol_wa.name = "wind_barb_100"
        symbol_wa.type = mapscript.MS_SYMBOL_VECTOR
        lo = mapscript.lineObj()
        lo.add(mapscript.pointObj(2,8.2))
        lo.add(mapscript.pointObj(26,8.2))
        symbol_wa.setPoints(lo)
        # symbol_wa.anchorpoint_x = 1.
        # symbol_wa.anchorpoint_y = 1.
        symbol_wa.filled = False
        symbol_obj.appendSymbol(symbol_wa)



        symbol_obj.save(symbol_file)
        created = True
    return created