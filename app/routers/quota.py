from fastapi import APIRouter, Depends
from ..schemas import QuotaOut
from ..security import ensure_client
from ..services.usage import get_quota
router=APIRouter(prefix="/api",tags=["quota"])
@router.get("/quota",response_model=QuotaOut)
def quota(client_id:str=Depends(ensure_client)):
    return QuotaOut(**get_quota(client_id))
