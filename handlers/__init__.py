from aiogram import Router

from . import common, core, vk, tg, settings, reports

router = Router()

# Порядок включения важен для правильного перехвата callback-ов и текстовых команд
router.include_router(common.router)
router.include_router(core.router)
router.include_router(vk.router)
router.include_router(tg.router)
router.include_router(settings.router)
router.include_router(reports.router)

# Обязательная подписка отключена: бот доступен без проверки канала.
