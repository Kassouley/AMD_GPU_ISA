import threading
import csv
import re
from ..ISA.ISA_Soup import ISA_Soup
from ..ISA.ISA_PDF import ISA_PDF
from ..InstructionData.Format import Format
from ..InstructionData.Instruction import Instruction
from ..utils.utils import *
from ..utils.enumeration import *

class InstructionSet :
    def __init__(self, isa_name: str, isa_llvm_urls: list[str] | str, 
                 isa_pdf_path: str, pdf_pages_range: range, pdf_is_double_optable: bool) -> None:
        
        self.isa_name = isa_name
        self.isa_llvm_urls = isa_llvm_urls
        self.isa_llvm_soup = ISA_Soup(isa_llvm_urls)
        self.isa_pdf = ISA_PDF(isa_pdf_path, self.get_pdf_table_format(), pdf_pages_range, pdf_is_double_optable)
        
        self.instructions_dict_lock = threading.Lock()

        self.instructions_dict: dict[str,list[Instruction]] = {}
        self.format_dict: dict[str,list[Format]] = {}

    def get_pdf_table_format(self) -> None:
        raise NotImplementedError("This method should be implemented in the subclass")
    
    def set_correct_format(self, instruction, instruction_format_str) -> None :
        raise NotImplementedError("This method should be implemented in the subclass")

    def set_correct_opcode(self, instruction: Instruction, instruction_format_str: str, instruction_former_format_str: str) -> None :
        raise NotImplementedError("This method should be implemented in the subclass")

    def set_corresponding_operand_to_field(self, instruction: Instruction) -> None:
        # Prepare encoding array
        encoding_string = instruction.get_encoding_string().replace(" ", ".").replace("-", "")
        encoding_arr = [e for e in encoding_string.split(".") if not all(c in '01' for c in e)]

        try :
            encoding_arr.remove("ACC")
            encoding_arr.remove("ACC0")
            encoding_arr.remove("ACC1")
            encoding_arr.remove("ACC2")
            encoding_arr.remove("SRC0_SEXT")
            encoding_arr.remove("SRC1_SEXT")
            encoding_arr.remove("SRC2_SEXT")
            encoding_arr.remove("SEXT")
            encoding_arr.remove("SRC0_NEG")
            encoding_arr.remove("SRC1_NEG")
            encoding_arr.remove("SRC2_NEG")
            encoding_arr.remove("NEG")
            encoding_arr.remove("SRC0_ABS")
            encoding_arr.remove("SRC1_ABS")
            encoding_arr.remove("SRC2_ABS")
            encoding_arr.remove("ABS")
            encoding_arr.remove("S0")
            encoding_arr.remove("S1")
        except: 
            pass
        
        # Get operands and modifiers
        operands = instruction.get_operand_list()
        modifiers = instruction.get_modifier_list()
        
        # Combine operands and modifiers into a single list with flags
        elements = [op for op in operands] + [mod for mod in modifiers]
        elements_len = len(elements)
        elements_found = [False] * elements_len
        
        max_iterations = elements_len * 3  # Prevent infinite loops
        iterations = 0
        # Main processing loop
        i = 0
        while elements_len > 0 and iterations < max_iterations:
            iterations += 1
            element = elements[i]
            if elements_found[i]:
                i = (i + 1) % len(elements)  # Wrap around
                continue
            
            element_name = element.get_name().upper()

            # Define a mapping for special cases
            special_cases = {
                'VDATA': 'VDATA0',
                'SDST': ['VDST', 'SDATA'],  # SDST maps to both 'VDST' and 'SDATA'
                'HWREG': 'SIMM16',
                'PROBE': 'SDATA',
                'OFFSET21S': 'OFFSET',
                'OFFSET20U': 'OFFSET',
                'OFFSET12': 'OFFSET',
                'OFFSET13S': 'OFFSET',
                'DPP64_CTRL': 'DPP_CTRL',
                'DPP32_CTRL': 'DPP_CTRL',
                'LABEL': 'SIMM16',
                'IMM16': 'SIMM16',
                'VDST': 'VDATA',
                'SRC': 'SRC0',
                'VSRC': 'SRC0',
                'VSRC0': 'SRC0',
                'VSRC1': 'SRC1',
                'VSRC2': 'SRC2',
                'SRC0': 'VSRC0',
                'SRC1': 'VSRC1',
                'SRC2': 'VSRC2',
                'SSRC0': 'SRC0',
                'SSRC1': 'SRC1',
                'SSRC2': 'SRC2',
                'SSRC': 'SSRC0',
                'M_OP_SEL': 'OP_SEL',
                'M_OP_SEL_HI': 'OP_SEL_HI'
            }

            # Check for matching conditions
            matched_field = None
            if len(encoding_arr) == 1:
                matched_field = encoding_arr[0]
            elif element_name in encoding_arr:
                matched_field = element_name
            elif element_name in special_cases:
                case_value = special_cases[element_name]
                if isinstance(case_value, list):  # Handle multiple mappings
                    for field in case_value:
                        if field in encoding_arr:
                            matched_field = field
                            break
                elif case_value in encoding_arr:
                    matched_field = case_value
            elif element_name == "VCC":
                element.set_corresponding_field("none")
                elements_found[i] = True
                elements_len -= 1
            elif element_name == "OP_SEL_HI":
                element.set_corresponding_field("OP_SEL_HI+OP_SEL_HI2")
                encoding_arr.remove("OP_SEL_HI")
                encoding_arr.remove("OP_SEL_HI2")
                elements_found[i] = True
                elements_len -= 1
            elif (element_name == "OFFSET" or element_name == "PATTERN") and "OFFSET0" in encoding_arr and "OFFSET1" in encoding_arr:
                element.set_corresponding_field("OFFSET0+OFFSET1")
                encoding_arr.remove("OFFSET0")
                encoding_arr.remove("OFFSET1")
                elements_found[i] = True
                elements_len -= 1
            elif element_name == "FMT" and "NFMT" in encoding_arr and "DFMT" in encoding_arr:
                element.set_corresponding_field("NFMT+DFMT")
                encoding_arr.remove("NFMT")
                encoding_arr.remove("DFMT")
                elements_found[i] = True
                elements_len -= 1

            # Perform assignment if a match is found
            if matched_field:
                element.set_corresponding_field(matched_field)
                encoding_arr.remove(matched_field)
                elements_found[i] = True
                elements_len -= 1

            # Move to the next element
            i = (i + 1) % len(elements)



    def create_instructions_dict_aux(self, instruction_mnemonic: str, instructions_info: list) :
        instruction_modifier_list = instructions_info.pop()
        instruction_operand_list = instructions_info.pop()
        instruction_type_src = instructions_info.pop()
        instruction_type_dst = instructions_info.pop()
        instruction_mnemonic_mangled = instructions_info.pop().upper()
        instruction_format_str = instructions_info.pop()
        instruction_type = instruction_type_src if instruction_operand_list else "-"
        instruction_note = ''
        instruction_former_format_str = None

        pdf_instruction_dict = self.isa_pdf.get_instructions_dict()
        instruction_data = pdf_instruction_dict.get(instruction_mnemonic_mangled)
        if instruction_data:
            instruction_opcode = instruction_data[ISA_Pdf.OPCODE.value]
            instruction_former_format_str = instruction_data[ISA_Pdf.FORMAT.value]
        else:
            print(f"No opcode found for: {instruction_mnemonic} ({instruction_format_str})")
            instruction_opcode = 'N/O'
            instruction_note = (f"No opcode found. Instruction exists in LLVM documentation "
                                f"({','.join(self.isa_llvm_urls)}) but not in {self.isa_name} documentation")

        
        # INSTRUCTION CREATION
        instruction = Instruction(mnemonic=instruction_mnemonic.upper(), 
                                  type=instruction_type, 
                                  operand_list=instruction_operand_list, 
                                  modifier_list=instruction_modifier_list,
                                  opcode=instruction_opcode,
                                  note=instruction_note)
        
        self.set_correct_opcode(instruction, instruction_format_str, instruction_former_format_str)
        self.set_correct_format(instruction, instruction_format_str)
        self.set_corresponding_operand_to_field(instruction)
        
        # INSTRUCTION ATOMIC ADD TO DIC
        with self.instructions_dict_lock:
            instruction_format_name = instruction.get_format_name()
            if instruction_format_name not in self.instructions_dict:
                self.instructions_dict[instruction_format_name] = []
            self.instructions_dict[instruction_format_name].append(instruction)


    def create_instructions_dict(self) -> None :
        self.create_format_dict()
        isa_llvm_soup_instruction_dict = self.isa_llvm_soup.get_instruction_dict()

        threads = []
        for instruction_mnemonic, instructions_info in isa_llvm_soup_instruction_dict.items() :
            t = threading.Thread(target=self.create_instructions_dict_aux, args=(instruction_mnemonic, instructions_info,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.add_no_match_instructions()


    def _get_field_name(self, field_dict, format_name, field_data) :
        return field_data[0]

    def create_format_dict(self) -> None:
        self.format_dict = {}
        
        for format_name, sub_dict in self.isa_pdf.get_scraped_data().items():
            field_dict = {}
            for field_data in sub_dict['FIELD']['tab'][1:] :
                field_name = self._get_field_name(field_dict, format_name, field_data)
                if field_name and field_name not in field_dict :
                    numbers = list(map(int, re.findall(r'\d+', field_data[1])))
                    if len(numbers) == 1:
                        bits_size = 1
                    else :
                        bits_size = numbers[-2] - numbers[-1] + 1
                    field_dict[field_name] = {'bits': field_data[1], 'size': bits_size, 'desc': field_data[2]}

            last_field_bits = list(field_dict.values())[-1]['bits']
            encoding_size = int(re.search(r'\[(\d+)', last_field_bits).group(1)) + 1 if last_field_bits else 0
            
            encoding_bits = "".join(re.findall(r'[01]+', field_dict.get('ENCODING', {}).get('desc', '')))
            
            self.format_dict[format_name] = Format(
                name=format_name,
                binary_encoding=encoding_bits,
                field_dict=field_dict,
                size=encoding_size
            )


    def add_no_match_instructions(self) -> None:
        pdf_instructions = self.isa_pdf.get_instructions_dict()

        existing_instructions = {
            instruction.get_mnemonic()
            for instructions_by_format in self.instructions_dict.values()
            for instruction in instructions_by_format
        }

        for pdf_instruction_mnemonic, pdf_instruction_details in pdf_instructions.items():
            if pdf_instruction_mnemonic not in existing_instructions:
                print(f"No match found for {pdf_instruction_mnemonic} "
                    f"({pdf_instruction_details[ISA_Pdf.OPCODE.value]}/"
                    f"{pdf_instruction_details[ISA_Pdf.FORMAT.value]})")

                new_instruction = Instruction(mnemonic=pdf_instruction_details[ISA_Pdf.INSTRUCTIONS.value], 
                                              format=self.format_dict[pdf_instruction_details[ISA_Pdf.FORMAT.value]], 
                                              type=None, 
                                              opcode=pdf_instruction_details[ISA_Pdf.OPCODE.value],
                                              operand_list=[], 
                                              modifier_list=[],
                                              note=(f"Instruction exists in {self.isa_name} documentation but "
                                                    f"not in LLVM documentation ({self.isa_llvm_urls})"))   
                self.instructions_dict[pdf_instruction_details[ISA_Pdf.FORMAT.value]].append(new_instruction)

    def formats_to_csv(self, csv_path: str) -> None:
        header = [["INSTRUCTION","SIZE","ENCODING","ENCODING_STRING",
                   "FIELD 0","BITS","FIELD 1","BITS","FIELD 2","BITS",
                   "FIELD 3","BITS","FIELD 4","BITS","FIELD 5","BITS",
                   "FIELD 6","BITS","FIELD 7","BITS","FIELD 8","BITS",
                   "FIELD 9","BITS","FIELD 10","BITS","FIELD 11","BITS",
                   "FIELD 12","BITS","FIELD 13","BITS","FIELD 14","BITS",
                   "FIELD 15","BITS","FIELD 16","BITS"]]
        with open(csv_path, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerows(header)
            for format in self.format_dict.values():
                csv_writer.writerow(format.to_list())


    def instructions_to_csv(self, csv_path: str) -> None:
        header = [["FORMAT","ENCODING","OPCODE","INSTRUCTIONS","TYPE",
                   "OPERAND0","OPERAND1","OPERAND2","OPERAND3","OPERAND4",
                   "MODIFIER0","MODIFIER1","MODIFIER2","MODIFIER3","MODIFIER4",
                   "MODIFIER5","MODIFIER6","MODIFIER7","NOTE"]]
        with open(csv_path, 'w', newline='') as csvfile:
            csv_writer = csv.writer(csvfile)
            csv_writer.writerows(header)
            for _, instructions in self.instructions_dict.items() :
                for instruction in instructions :
                    operands_field = [
                        f"{op.get_corresponding_field()}:"
                        f"{op.get_name()}:"
                        f"{op.get_role()}:"
                        f"{op.get_type()}:"
                        f"{op.get_size()}:"
                        f"{op.is_vector_or_scalar()}:"
                        f"{'OPT' if op.is_optional() else 'REQ'}"
                        for op in instruction.get_operand_list()
                    ]
                    operands_field.extend([''] * (5 - len(operands_field)))

                    modifier_field = [
                        f"{mod.get_corresponding_field()}:"
                        f"{mod.get_name()}"
                        for mod in instruction.get_modifier_list()
                    ]
                    modifier_field.extend([''] * (8 - len(modifier_field)))
                    row = [[
                        instruction.get_format_name(),
                        instruction.get_encoding_string(),
                        instruction.get_opcode(),
                        instruction.get_mnemonic(),
                        instruction.get_type()
                        ] + operands_field + modifier_field + [
                        instruction.get_note()
                    ]]
                    csv_writer.writerows(row)