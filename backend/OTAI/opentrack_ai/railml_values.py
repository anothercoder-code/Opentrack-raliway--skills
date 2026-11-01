"""Reviewed original rolling-stock XML numeric helpers; no simulation loop."""
import math
import re
import struct

from .archive import APIError

INT_MIN=-2147483648
INT_MAX=2147483647
INTEGER=re.compile(r'^[\t\r\n\f\v ]*([+-]?[0-9]+)')
REAL=re.compile(r'^[\t\r\n\f\v ]*([+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)')


def checked_int(value):
    if not INT_MIN<=value<=INT_MAX:raise APIError('ROLLING_STOCK_XML_NUMBER','A numeric value exceeds the audited signed-int32 domain.',str(value)[:80])
    return int(value)


def f32(value):
    try:result=struct.unpack('<f',struct.pack('<f',value))[0]
    except (OverflowError,struct.error) as error:raise APIError('ROLLING_STOCK_XML_NUMBER','A value exceeds finite native float32.') from error
    if not math.isfinite(result):raise APIError('ROLLING_STOCK_XML_NUMBER','Nonfinite native numeric input is not accepted.')
    return result


def int_text(text):
    match=INTEGER.match(text);return checked_int(int(match.group(1))) if match else 0


def float_text(text):
    if re.match(r'^[\t\r\n\f\v ]*[+-]?(?:nan|inf)',text,re.I):raise APIError('ROLLING_STOCK_XML_NUMBER','Nonfinite numeric spellings are outside the audited XML domain.')
    match=REAL.match(text);return f32(float(match.group(1))) if match else 0.0


def native_truncate(value):
    if not math.isfinite(value):raise APIError('ROLLING_STOCK_XML_NUMBER','A nonfinite value cannot become a saved integer.')
    return checked_int(math.trunc(value))


def i32(value):return (int(value)+2147483648)%4294967296-2147483648


def c_divide(numerator,denominator):
    if denominator==0 or numerator==INT_MIN and denominator==-1:
        raise APIError('ENGINE_CURVE_ARITHMETIC','The original integer curve formula would divide by zero or overflow.')
    return (abs(numerator)//abs(denominator))*(-1 if (numerator<0)!=(denominator<0) else 1)


def speed_max(rows):return max([0,*[row[0] for row in rows]])


def traction_at(rows,speed):
    """OTEngine 0x4cbeb8: integer arithmetic, original order and sentinels."""
    if speed<0 or speed>speed_max(rows) or not rows:return 0
    if speed==0:return rows[0][1]
    lower_x=lower_y=-1;upper_x=upper_y=32000;kind=1
    for x,y,flag in rows:
        if speed<x:
            if x<upper_x:upper_x=x;upper_y=y;kind=flag
        elif lower_x<x:
            lower_x=x;lower_y=y
        elif speed==x:
            lower_x=upper_x=speed;lower_y=upper_y=y;kind=flag;break
    if lower_x==-1:lower_x=upper_x;lower_y=upper_y
    elif upper_x==32000:upper_x=lower_x;upper_y=lower_y
    if lower_x==upper_x:return upper_y
    if kind==1:
        return i32(c_divide(i32(i32(speed-lower_x)*i32(lower_y-upper_y)),i32(lower_x-upper_x))+lower_y)
    numerator=i32(i32(i32(lower_x*upper_x)*i32(lower_y-upper_y))+i32(i32(i32(upper_x*upper_y)-i32(lower_x*lower_y))*speed))
    return c_divide(numerator,i32(i32(upper_x-lower_x)*speed))


def sampled_traction(rows,speed,engine_maximum):
    
    
    last=i32(engine_maximum+1)
    if last<0:return 0.0
    return f32(traction_at(rows,min(speed,last)))


def diagram_power_w(rows):
    
    
    largest=0.0
    for speed,force,_ in rows:
        value=f32((speed/3.6)*i32(force*1000))
        if largest<value:largest=value
    return native_truncate(largest)


def imported_points(points,x_name,y_name):
    
    
    rows=[];last_speed=-1;skipped=0
    for speed,force in points:
        speed=f32(speed*3.6) if x_name.lower() in ['m/s','ms'] else speed
        if y_name.lower()=='kn':force=force*1000.0
        speed=native_truncate(speed);force=native_truncate(force/1000.0)
        if last_speed==speed:skipped+=1;continue
        rows.append((speed,force,1));last_speed=speed
    return rows,skipped
