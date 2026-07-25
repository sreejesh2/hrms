"""
Reusable queryset / view helpers to avoid N+1 and keep list views consistent.
"""

from django.db import models


class RelatedQuerySet(models.QuerySet):
    """
    Base QuerySet. Subclasses should override `list_related` / `detail_related`
    so callers can do Model.objects.for_list() without forgetting joins.
    """

    list_select_related: tuple[str, ...] = ()
    list_prefetch_related: tuple[str, ...] = ()
    detail_select_related: tuple[str, ...] = ()
    detail_prefetch_related: tuple[str, ...] = ()

    def for_list(self):
        qs = self
        if self.list_select_related:
            qs = qs.select_related(*self.list_select_related)
        if self.list_prefetch_related:
            qs = qs.prefetch_related(*self.list_prefetch_related)
        return qs

    def for_detail(self):
        qs = self
        if self.detail_select_related:
            qs = qs.select_related(*self.detail_select_related)
        if self.detail_prefetch_related:
            qs = qs.prefetch_related(*self.detail_prefetch_related)
        return qs


class RelatedManager(models.Manager):
    def get_queryset(self):
        return RelatedQuerySet(self.model, using=self._db)

    def for_list(self):
        return self.get_queryset().for_list()

    def for_detail(self):
        return self.get_queryset().for_detail()


class PaginatedListMixin:
    """CBV mixin: paginate get_queryset() results via shared helper."""

    paginate_by = 25
    page_kwarg = "page"
    context_object_list_name = "object_list"

    def paginate_queryset(self, queryset):
        from core.pagination import paginate

        return paginate(
            self.request, queryset, per_page=self.paginate_by, page_param=self.page_kwarg
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if "object_list" in context and not context.get("page_obj"):
            page_obj = self.paginate_queryset(context["object_list"])
            context["page_obj"] = page_obj
            context[self.context_object_list_name] = page_obj.object_list
            context["paginator"] = page_obj.paginator
        return context
