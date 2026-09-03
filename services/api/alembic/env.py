import asyncio
from logging.config import fileConfig

from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context
from app.config import settings
from app.models_registry import Base  # noqa: F401 - import để nạp toàn bộ metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# `alembic check` so metadata với DB thật. Trong DB thật còn có những thứ KHÔNG do chúng ta
# tạo và không mô tả được bằng model, nên nếu không lọc thì check luôn đỏ:
#
#   - Bảng của extension: PostGIS (spatial_ref_sys), và bộ TIGER geocoder trong ảnh
#     postgis/postgis mà CI dùng (cousub, place, county… — search_path có cả schema `tiger`
#     nên chúng lọt vào lượt reflect ở schema mặc định).
#   - ix_driver_profiles_geo: index GIST trên biểu thức geography(ST_MakePoint(...)), viết
#     bằng SQL thô ở migration 0001 vì SQLAlchemy không diễn đạt được index theo biểu thức.
#
# Quy tắc: KHÔNG bao giờ đề xuất xoá một bảng mà model chưa từng biết tới. Đánh đổi đã cân
# nhắc — nếu ai đó xoá một model mà quên viết migration, check sẽ không bắt được. Nhưng xoá
# bảng vốn phải là quyết định có chủ đích kèm migration, còn một cổng kiểm tra đỏ vĩnh viễn
# thì tệ hơn nhiều: không ai đọc nó nữa, và lần nó báo thay đổi thật thì cũng không ai nghe.
IGNORED_INDEXES = {"ix_driver_profiles_geo"}


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    if type_ == "table" and reflected and name not in target_metadata.tables:
        return False
    if type_ == "index":
        return name not in IGNORED_INDEXES
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
