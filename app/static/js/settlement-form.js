(() => {
  const form = document.querySelector("#settlement-form");
  if (!form) return;

  const itemsRoot = document.querySelector("#expense-items");
  const evidenceInput = document.querySelector("#evidence_files");
  const mappingRoot = document.querySelector("#file-mapping");
  const errorsRoot = document.querySelector("#form-errors");
  const totalRoot = document.querySelector("#claimed-total");
  const evidenceCount = document.querySelector("#evidence-count");
  const submitButton = document.querySelector("#submit-button");
  let itemSequence = 0;
  let selectedEvidenceFiles = [];
  const evidenceTargets = new Map();

  const categories = [
    ["CLIENT_MEAL", "Ăn uống / tiếp khách"],
    ["TRAVEL", "Công tác / di chuyển"],
    ["HOTEL", "Khách sạn"],
    ["TAXI", "Taxi / xe công nghệ"],
    ["OFFICE_SUPPLIES", "Văn phòng phẩm"],
    ["OPERATIONS", "Chi phí vận hành"],
    ["PERSONAL", "Chi tiêu cá nhân"],
    ["OTHER", "Khác"],
  ];

  function money(value) {
    return new Intl.NumberFormat("vi-VN").format(Number(value || 0)) + " VND";
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function fileKey(file) {
    return file.name.toLocaleLowerCase("vi");
  }

  function addExpense() {
    itemSequence += 1;
    const id = "ITEM-" + String(itemSequence).padStart(3, "0");
    const categoryOptions = categories.map((entry) =>
      '<option value="' + entry[0] + '">' + entry[1] + "</option>"
    ).join("");
    const node = document.createElement("div");
    node.className = "expense-row";
    node.dataset.itemId = id;
    node.innerHTML =
      '<div class="expense-row-header"><strong>' + id +
      '</strong><button class="remove-expense" type="button">Xóa</button></div>' +
      '<div class="form-grid">' +
      '<div class="field span-2"><label>Nội dung khoản chi</label>' +
      '<input class="item-description" type="text" placeholder="Tiếp khách trưa ngày 16/10"></div>' +
      '<div class="field"><label>Danh mục</label><select class="item-category">' +
      categoryOptions + '</select></div>' +
      '<div class="field"><label>Ngày chi</label><input class="item-date" type="date"></div>' +
      '<div class="field"><label>Số tiền khai báo</label>' +
      '<input class="item-amount" type="number" min="1" step="1" placeholder="1200000"></div>' +
      '<div class="field"><label>Mã ngoại lệ (nếu không có chứng từ)</label>' +
      '<input class="item-exception" type="text" placeholder="Để trống nếu có chứng từ"></div></div>';
    node.querySelector(".remove-expense").addEventListener("click", () => {
      if (itemsRoot.children.length === 1) return;
      node.remove();
      renderFileMapping();
      updateTotal();
    });
    node.querySelector(".item-amount").addEventListener("input", updateTotal);
    node.querySelector(".item-description").addEventListener("input", renderFileMapping);
    itemsRoot.appendChild(node);
    renderFileMapping();
  }

  function itemOptions(selectedValue) {
    return [...itemsRoot.querySelectorAll(".expense-row")].map((row) => {
      const description = row.querySelector(".item-description").value || "Chưa nhập nội dung";
      const selected = row.dataset.itemId === selectedValue ? " selected" : "";
      return '<option value="' + escapeHtml(row.dataset.itemId) + '"' + selected + ">" +
        escapeHtml(row.dataset.itemId + " · " + description) + "</option>";
    }).join("");
  }

  function renderFileMapping() {
    mappingRoot.querySelectorAll("select").forEach((select) => {
      evidenceTargets.set(select.dataset.fileKey, select.value);
    });
    if (!selectedEvidenceFiles.length) {
      evidenceCount.textContent = "Chưa chọn file";
      mappingRoot.className = "file-mapping empty";
      mappingRoot.textContent = "Chưa có chứng từ được chọn.";
      return;
    }
    evidenceCount.textContent = selectedEvidenceFiles.length + " file đã chọn";
    mappingRoot.className = "file-mapping";
    mappingRoot.innerHTML = selectedEvidenceFiles.map((file, index) => {
      const key = fileKey(file);
      const previous = evidenceTargets.get(key) || "";
      return '<div class="file-map-row"><div><strong>' + escapeHtml(file.name) +
        "</strong><small>" + (file.size / 1024).toFixed(1) +
        ' KB</small></div><div class="file-map-actions"><select class="file-target" data-file-key="' +
        escapeHtml(key) + '" data-filename="' + escapeHtml(file.name) +
        '"><option value="">Chọn khoản chi liên quan</option>' +
        itemOptions(previous) + '</select><button class="remove-file" type="button" data-file-index="' +
        index + '" aria-label="Bỏ chứng từ ' + escapeHtml(file.name) + '">×</button></div></div>';
    }).join("");
    mappingRoot.querySelectorAll(".file-target").forEach((select) => {
      evidenceTargets.set(select.dataset.fileKey, select.value);
      select.addEventListener("change", () => {
        evidenceTargets.set(select.dataset.fileKey, select.value);
      });
    });
    mappingRoot.querySelectorAll(".remove-file").forEach((button) => {
      button.addEventListener("click", () => {
        const index = Number(button.dataset.fileIndex);
        const removed = selectedEvidenceFiles[index];
        if (removed) evidenceTargets.delete(fileKey(removed));
        selectedEvidenceFiles.splice(index, 1);
        renderFileMapping();
      });
    });
  }

  function updateTotal() {
    const total = [...itemsRoot.querySelectorAll(".item-amount")]
      .reduce((sum, input) => sum + Number(input.value || 0), 0);
    totalRoot.textContent = money(total);
  }

  function value(id) {
    const result = document.querySelector("#" + id).value.trim();
    return result || null;
  }

  function buildPayload() {
    const evidenceByItem = {};
    selectedEvidenceFiles.forEach((file) => {
      const target = evidenceTargets.get(fileKey(file));
      if (!target) return;
      evidenceByItem[target] ||= [];
      evidenceByItem[target].push(file.name);
    });
    const expenseItems = [...itemsRoot.querySelectorAll(".expense-row")].map((row) => ({
      item_id: row.dataset.itemId,
      category: row.querySelector(".item-category").value,
      description: row.querySelector(".item-description").value.trim(),
      expense_date: row.querySelector(".item-date").value || null,
      claimed_amount: row.querySelector(".item-amount").value || "0",
      currency: "VND",
      evidence_names: evidenceByItem[row.dataset.itemId] || [],
      policy_exception_code: row.querySelector(".item-exception").value.trim() || null,
    }));
    const settlementType = form.querySelector("[name=settlement_type]:checked").value;
    return {
      settlement_type: settlementType,
      source_type: form.querySelector("[name=source_type]:checked").value,
      employee: {
        employee_id: "EMP-DEMO-001",
        name: "Nguyễn Minh An",
        department: "Phòng Kinh doanh",
        position: "Nhân viên",
        data_classification: "SYNTHETIC",
      },
      business_context: {
        purpose: value("purpose") || "",
        project_code: value("project_code"),
        client_name: value("client_name"),
        activity_start_date: value("activity_start_date"),
        activity_end_date: value("activity_end_date"),
      },
      advance_id: settlementType === "ADVANCE_SETTLEMENT" ? value("advance_id") : null,
      allocated_advance_amount: settlementType === "ADVANCE_SETTLEMENT"
        ? document.querySelector("#allocated_advance_amount").value || "0"
        : "0",
      currency: "VND",
      expense_items: expenseItems,
    };
  }

  function showErrors(issues) {
    errorsRoot.classList.remove("hidden");
    errorsRoot.textContent = issues.join("\n");
    errorsRoot.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  document.querySelector("#add-expense").addEventListener("click", addExpense);
  evidenceInput.addEventListener("change", () => {
    [...evidenceInput.files].forEach((file) => {
      const key = fileKey(file);
      const existingIndex = selectedEvidenceFiles.findIndex(
        (selected) => fileKey(selected) === key
      );
      if (existingIndex >= 0) {
        selectedEvidenceFiles[existingIndex] = file;
      } else {
        selectedEvidenceFiles.push(file);
      }
    });
    evidenceInput.value = "";
    renderFileMapping();
  });
  form.querySelectorAll("[name=settlement_type]").forEach((input) => {
    input.addEventListener("change", () => {
      document.querySelector("#advance-fields").classList.toggle(
        "hidden",
        input.value !== "ADVANCE_SETTLEMENT" || !input.checked
      );
    });
  });
  form.querySelectorAll("[name=source_type]").forEach((input) => {
    input.addEventListener("change", () => {
      document.querySelector("#paper-form-field").classList.toggle(
        "hidden",
        input.value !== "PAPER_SCAN" || !input.checked
      );
    });
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorsRoot.classList.add("hidden");
    const payload = buildPayload();
    const localIssues = [];
    payload.expense_items.forEach((item) => {
      if (!item.description) {
        localIssues.push(item.item_id + ": chưa nhập nội dung khoản chi.");
      }
      if (Number(item.claimed_amount) <= 0) {
        localIssues.push(item.item_id + ": số tiền phải lớn hơn 0.");
      }
    });
    if (localIssues.length) {
      showErrors(localIssues);
      return;
    }
    const body = new FormData();
    body.append("payload", JSON.stringify(payload));
    const formFile = document.querySelector("#settlement_form_file").files[0];
    if (formFile) body.append("settlement_form", formFile);
    selectedEvidenceFiles.forEach((file) => body.append("evidence_files", file));

    submitButton.disabled = true;
    submitButton.textContent = "Đang gửi...";
    try {
      const response = await fetch("/api/v1/settlements", {
        method: "POST",
        body,
      });
      const result = await response.json();
      if (!response.ok) {
        showErrors(result.issues || [result.detail || "Không thể gửi hồ sơ."]);
        return;
      }
      window.location.assign("/employee/settlements/" + result.case_id);
    } catch (error) {
      showErrors(["Không kết nối được máy chủ. Vui lòng thử lại."]);
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Gửi hồ sơ";
    }
  });

  addExpense();
})();
